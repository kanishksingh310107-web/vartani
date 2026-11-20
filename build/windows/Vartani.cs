using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class Vartani
{
    internal static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
    internal static string Profile
    {
        get
        {
            var home = Environment.GetEnvironmentVariable("VARTANI_HOME");
            var data = Environment.GetEnvironmentVariable("VARTANI_DATA");
            if (!String.IsNullOrWhiteSpace(home)) return Path.GetFullPath(home);
            if (!String.IsNullOrWhiteSpace(data)) return Directory.GetParent(Path.GetFullPath(data)).FullName;
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Vartani");
        }
    }

    internal static Process StartWorker(string entry, string options)
    {
        string app = Path.Combine(Root, "app");
        string script = Path.Combine(app, entry);
        string python = Path.Combine(Root, "python", "python.exe");
        if (!File.Exists(script) || !File.Exists(python))
            throw new IOException("Vartani is missing application files. Run the installer again.");
        var start = new ProcessStartInfo(python)
        {
            Arguments = "-E -s -B -u \"" + script + "\"" + options,
            UseShellExecute = false,
            WorkingDirectory = app,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        start.EnvironmentVariables["VARTANI_PACKAGED"] = "1";
        return Process.Start(start);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 2 && args[0] == "--smoke-test")
            {
                using (var process = StartWorker("launcher.py", " --smoke-test \"" + Path.GetFullPath(args[1]) + "\""))
                {
                    if (process.WaitForExit(60000)) return process.ExitCode;
                    process.Kill();
                    return 1;
                }
            }
            bool windowCheck = args.Length == 2 && args[0] == "--window-check";
            if (args.Length != 0 && !windowCheck) return 2;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Directory.CreateDirectory(Profile);
            // Profiles must not have two desktop servers writing simultaneously.
            using (var setupGuard = new Mutex(false, @"Local\VartaniDesktopInstallerGuard"))
            using (var profileLock = new FileStream(Path.Combine(Profile, ".desktop.lock"), FileMode.OpenOrCreate, FileAccess.Write, FileShare.None))
            using (var window = new MainWindow(windowCheck ? Path.GetFullPath(args[1]) : null))
            {
                Application.Run(window);
                return window.ExitCode;
            }
        }
        catch (Exception e)
        {
            if (args.Length == 0) MessageBox.Show(e.Message + "\n\nIf Vartani is already open for this profile, use its existing window.", "Vartani could not open", MessageBoxButtons.OK, MessageBoxIcon.Error);
            else if (args.Length == 2 && args[0] == "--window-check") File.WriteAllText(args[1], "FAIL: " + e.Message);
            return 1;
        }
    }
}

internal sealed class MainWindow : Form
{
    private const string RuntimeHelp = "https://developer.microsoft.com/microsoft-edge/webview2/";
    private readonly string checkFile;
    private readonly Label status;
    private readonly MenuStrip menu;
    private WebView2 view;
    private Process worker;
    private Uri origin;
    private bool closing;
    private bool failed;
    internal int ExitCode { get; private set; }

    internal MainWindow(string checkFile)
    {
        this.checkFile = checkFile;
        Text = "Vartani";
        Width = 1300;
        Height = 900;
        MinimumSize = new Size(780, 540);
        StartPosition = FormStartPosition.CenterScreen;
        status = new Label { Dock = DockStyle.Fill, Text = "Starting Vartani…", TextAlign = ContentAlignment.MiddleCenter };
        menu = new MenuStrip();
        var app = new ToolStripMenuItem("Vartani");
        app.DropDownItems.Add("Home", null, (s,e) => Go("/"));
        app.DropDownItems.Add("Back", null, (s,e) => { if (view != null && view.CanGoBack) view.GoBack(); });
        app.DropDownItems.Add("Install or repair WebView2…", null, (s,e) => OpenExternal(new Uri(RuntimeHelp)));
        app.DropDownItems.Add("Exit", null, (s,e) => Close());
        menu.Items.Add(app);
        Controls.Add(status);
        Controls.Add(menu);
        MainMenuStrip = menu;
        Shown += async (s,e) => await Boot();
        FormClosing += (s,e) => { closing = true; StopWorker(); };
    }

    private async Task Boot()
    {
        try
        {
            try
            {
                if (String.IsNullOrEmpty(CoreWebView2Environment.GetAvailableBrowserVersionString()))
                    throw new InvalidOperationException();
            }
            catch (Exception)
            {
                throw new InvalidOperationException("Microsoft Edge WebView2 Runtime is missing. Use Vartani → Install or repair WebView2, then restart Vartani.");
            }
            worker = Vartani.StartWorker("desktop_server.py", "");
            var errors = worker.StandardError.ReadToEndAsync();
            var ready = worker.StandardOutput.ReadLineAsync();
            if (await Task.WhenAny(ready, Task.Delay(45000)) != ready)
                throw new IOException("The local server did not start within 45 seconds. Check the profile logs and try again.");
            if (closing) return;
            string line = await ready;
            int port;
            if (line == null || !line.StartsWith("READY ", StringComparison.Ordinal) ||
                !Int32.TryParse(line.Substring(6), out port) || port < 1 || port > 65535)
                throw new IOException("Could not start the local server. " + (errors.IsCompleted ? errors.Result.Trim() : "Check the profile logs."));
            var remainingOutput = worker.StandardOutput.ReadToEndAsync();
            origin = new Uri("http://127.0.0.1:" + port);
            worker.EnableRaisingEvents = true;
            worker.Exited += (s,e) =>
            {
                if (!closing && !IsDisposed && IsHandleCreated)
                    try { BeginInvoke(new Action(() => { if (!closing) Fail("The local server stopped. Restart Vartani to continue."); })); }
                    catch (InvalidOperationException) { }
            };
            var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Vartani.Profile, "webview2"));
            if (closing) return;
            view = new WebView2 { Dock = DockStyle.Fill };
            Controls.Add(view);
            view.BringToFront();
            menu.BringToFront();
            await view.EnsureCoreWebView2Async(env);
            if (closing) return;
            var core = view.CoreWebView2;
            core.Settings.AreHostObjectsAllowed = false;
            core.Settings.IsWebMessageEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.NavigationStarting += (s,e) => { if (!IsLocal(e.Uri)) e.Cancel = true; };
            core.FrameNavigationStarting += (s,e) => { if (!IsLocal(e.Uri)) e.Cancel = true; };
            core.NewWindowRequested += (s,e) =>
            {
                e.Handled = true;
                if (e.IsUserInitiated && IsLocal(e.Uri)) core.Navigate(e.Uri);
            };
            core.DownloadStarting += (s,e) =>
            {
                if (!IsLocal(e.DownloadOperation.Uri)) { e.Cancel = true; return; }
                var deferral = e.GetDeferral();
                BeginInvoke(new Action(() =>
                {
                    try
                    {
                        using (var dialog = new SaveFileDialog { FileName = Path.GetFileName(e.ResultFilePath), OverwritePrompt = true })
                        {
                            e.Handled = true;
                            if (dialog.ShowDialog(this) == DialogResult.OK) e.ResultFilePath = dialog.FileName;
                            else e.Cancel = true;
                        }
                    }
                    finally { deferral.Complete(); }
                }));
            };
            core.NavigationCompleted += async (s,e) =>
            {
                if (!e.IsSuccess) { Fail("The Vartani page did not load. Restart the app and check the profile logs."); return; }
                if (this.checkFile == null || closing || failed) return;
                try
                {
                    for (int i = 0; i < 40; i++)
                    {
                        string rendered = await core.ExecuteScriptAsync("Boolean(document.querySelector('#root h1') && document.title.includes('Vartani'))");
                        if (closing) return;
                        if (rendered == "true")
                        {
                            // The test driver can verify the private endpoint before closing via the window.
                            File.WriteAllText(this.checkFile, "PASS " + origin.AbsoluteUri + Environment.NewLine);
                            return;
                        }
                        await Task.Delay(250);
                    }
                    Fail("The Vartani interface was not rendered.");
                }
                catch (Exception err) { if (!closing) Fail(err.Message); }
            };
            Go("/");
        }
        catch (Exception error) { if (!closing) Fail(error.Message); }
    }

    private bool IsLocal(string address)
    {
        Uri candidate;
        return origin != null && Uri.TryCreate(address, UriKind.Absolute, out candidate) &&
            candidate.Scheme == origin.Scheme && candidate.Host == origin.Host &&
            candidate.Port == origin.Port && candidate.UserInfo.Length == 0;
    }

    private void Go(string path)
    {
        if (view != null && view.CoreWebView2 != null) view.CoreWebView2.Navigate(new Uri(origin, path).AbsoluteUri);
    }

    private void OpenExternal(Uri url)
    {
        try { Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true }); }
        catch (Exception e) { MessageBox.Show(this, e.Message, "Could not open the help page"); }
    }

    private void Fail(string message)
    {
        if (failed) return;
        failed = true;
        ExitCode = 1;
        StopWorker();
        if (view != null) view.Visible = false;
        status.Text = message;
        if (checkFile != null)
        {
            File.WriteAllText(checkFile, "FAIL: " + message + Environment.NewLine);
            Close();
        }
    }

    private void StopWorker()
    {
        var process = worker;
        worker = null;
        if (process == null) return;
        try
        {
            if (!process.HasExited)
            {
                process.StandardInput.Close();
                if (!process.WaitForExit(3000)) process.Kill();
            }
        }
        catch (InvalidOperationException) { }
        finally { process.Dispose(); }
    }
}
