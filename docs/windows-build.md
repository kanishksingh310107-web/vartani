# Windows installer and desktop app

Run **VartaniSetup-x64.exe**, then open **Vartani** from the Windows Start menu. The app opens in its own window and uses the account's Microsoft Edge WebView2 rendering runtime. You do not need to extract a ZIP, install Python or Node.js, or open a browser tab.

The installer is per Windows account and defaults to `%LOCALAPPDATA%\Programs\Vartani`. It targets x64 Windows 10 (1809 or later) and Windows 11; this release was tested on the current Windows computer only. If Setup says WebView2 is missing, install Microsoft's [Evergreen WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) and retry. With WebView2 already present, the core app installs and starts offline.

## Profiles, upgrades, and uninstall

Vartani continues to use `%LOCALAPPDATA%\Vartani` for settings, runs, logs, and optional support. The installer and uninstaller do not touch that folder. Exit the app, then run the new installer to upgrade. Users switching from an earlier ZIP can open the installed version and continue using the same profile. Vartani migrates old saved keys to Windows account encryption. See [credential migration](credential-migration.md).

For a source checkout whose data is stored in its repository, use the ZIP launcher's **Import old Vartani data** feature or copy an old profile into a new empty profile before first opening the desktop app. Do not overwrite existing settings. Read the migration guide before moving a profile between Windows accounts or PCs.

## Optional downloads

- Hosted model connections need the provider's key and internet access. They don't use optional downloads.
- Hugging Face models can download **local-model support** in Test lab. The first model test downloads any missing weights. Gated models may require approval and a read token.
- In Speech check, use **Install speech support**. Whisper weights download separately on the first transcription and are reused. You can record in the app with Windows microphone permission or upload an audio file.
- Ollama and LM Studio are separate applications; Vartani connects to an already running local server.

## Build and test

Build with x64 Windows, Node.js/npm, the Windows .NET Framework C# compiler, and [Inno Setup 6.7](https://github.com/jrsoftware/issrc/releases). Install the build-time tools only on the build machine.

```powershell
npm.cmd --prefix frontend ci
.\build\windows\build.ps1 -InnoCompiler 'C:\path\to\ISCC.exe'
```

The build runs JavaScript and Python tests, checks bundled imports and assets, compiles the WinForms shell, and produces `VartaniSetup-x64.exe`. It pins and verifies Python and the wheel carrying the WebView2 assemblies. Set `-RuntimeArchive`, `-WebViewWheel`, or `-Wheelhouse` to reuse local inputs. If the checkout path is long and Inno Setup cannot find a staged file, use `-ArtifactRoot` to put the build under a shorter writable path.

On a disposable Windows account without a Vartani installer entry, run `python tests/desktop_smoke.py <installer> <new-short-test-folder>`. This tests first launch, the actual rendered interface, legacy profile upgrade, encrypted credentials, repeat launch, downloads from the reports API, and uninstall retention. Pass a WAV clip to also exercise real package installs and Whisper. The test can copy existing public Whisper weights into the temporary cache with `--cache`.

## Troubleshooting

- **Missing or damaged files:** run Setup again.
- **Saved connection needs a key:** open Test lab, edit the saved model, and re-enter the credential. This is expected after copying an encrypted profile to a different account.
- **Vartani cannot start:** close any other Vartani window using the same profile, check free space, and look at `%LOCALAPPDATA%\Vartani\logs\desktop.log`. Set `VARTANI_HOME` to a separate writable folder only if you intend to use another profile.
- **Windows flags an unknown publisher:** this local build is unsigned. Only install a copy from a source you trust; the release includes a SHA-256 digest to check file integrity.
