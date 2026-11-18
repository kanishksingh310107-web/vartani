using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Vartani
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string app = Path.Combine(root, "app");
            string entry = Path.Combine(app, "launcher.py");
            bool smokeTest = args.Length == 2 && args[0] == "--smoke-test";
            if (args.Length != 0 && !smokeTest) return 2;
            string interpreter = Path.Combine(root, "python", smokeTest ? "python.exe" : "pythonw.exe");
            if (!File.Exists(entry) || !File.Exists(interpreter))
                throw new IOException("Vartani's files are incomplete. Extract the complete ZIP into a new folder and try again.");

            var start = new ProcessStartInfo(interpreter)
            {
                Arguments = "-E -s -B \"" + entry + "\"" +
                    (smokeTest ? " --smoke-test \"" + Path.GetFullPath(args[1]) + "\"" : ""),
                WorkingDirectory = app,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            start.EnvironmentVariables["VARTANI_PACKAGED"] = "1";
            using (var process = Process.Start(start))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            if (args.Length == 0)
                MessageBox.Show(error.Message, "Vartani could not start", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
