from pathlib import Path
import sys
import zipfile

wheel, output = map(Path, sys.argv[1:3])
files = {
    "webview/lib/Microsoft.Web.WebView2.Core.dll": "Microsoft.Web.WebView2.Core.dll",
    "webview/lib/Microsoft.Web.WebView2.WinForms.dll": "Microsoft.Web.WebView2.WinForms.dll",
    "webview/lib/runtimes/win-x64/native/WebView2Loader.dll": "WebView2Loader.dll",
    "pywebview-6.2.1.dist-info/licenses/LICENSE": "pywebview-LICENSE.txt",
}
with zipfile.ZipFile(wheel) as archive:
    for name, target in files.items():
        (output / target).write_bytes(archive.read(name))
