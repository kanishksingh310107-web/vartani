# Windows launcher

Vartani now has a Windows-first, per-user launcher package. The package bundles the core app, Python runtime, and its locked core dependencies. End users do not need to install Python, Node.js, or run a terminal command.

## Build the Windows package

Build on 64-bit Windows with Python 3.11 installed on the **build machine**. Open PowerShell in the repository and run:

```powershell
.\build\windows\build.ps1
```

The script creates an isolated build environment, installs the exact versions in `requirements-windows.lock`, runs the core and launcher checks, builds the PyInstaller one-folder app, starts the packaged executable in smoke-test mode, and creates a timestamped ZIP in `artifacts\`. It refuses to overwrite an existing artifact. A failed pip/build step can be retried by running the same script again; the build environment is reused and completed user data is never touched.

Building requires internet access to install the locked Python build dependencies. The generated app itself does not download Python or its core dependencies.

## Install and launch

1. Download the ZIP and use Windows Explorer’s **Extract all** to unpack it into a writable folder, for example `Documents\Vartani-1.0.0`.
2. Open the extracted `Vartani` folder and double-click `Vartani.exe`.
3. The launcher checks the bundled files, prepares the profile, starts the local server, and opens the browser. If the browser does not open, use the URL shown in the launcher.
4. On later launches, double-click `Vartani.exe` again. Close the launcher to stop Vartani.

Extract each new version into a **new folder**. The launcher stores settings, model connections, suites, logs, and runs in `%LOCALAPPDATA%\Vartani`, outside the app folder, so they persist across launches and app-folder updates. Use **Import old Vartani data…** to copy `user` and `runs` from a previous project `data` folder. Import is copy-only: source files are left in place, and destination files are never overwritten. Removing the extracted app folder does not remove the profile.

The launcher shows actionable messages for missing package files, unwritable/full profile storage, occupied ports, server startup timeouts, and browser-opening failures. Setup is offline apart from the local browser connection. If the profile folder cannot be written, free disk space or set a writable `VARTANI_HOME` environment variable and retry.

## Internet and optional model requirements

- **Core installation and startup:** no internet connection required.
- **Hosted models** such as Groq or OpenAI: Vartani needs internet access when testing or running them, plus a user-provided API key.
- **Local model servers** such as Ollama/LM Studio: the server must be installed and running separately. Vartani does not install or download those models.
- **Hugging Face local models:** PyTorch/Transformers are not bundled. Install them only if wanted, using the instructions in the Test lab. Model weights download only when the user selects and tests a model.
- **Speech check:** Whisper/faster-whisper is not bundled. The user can opt in from the Speech check instructions; the chosen speech model downloads on first transcription.

The standard Windows package intentionally excludes PyTorch, Transformers, Faster Whisper, and CTranslate2 to keep setup smaller and avoid downloading optional model weights automatically.

## Troubleshooting

- **“Incomplete application files”:** extract the complete ZIP again into a new folder; do not run the EXE from inside the ZIP preview.
- **Profile write or storage error:** use a writable folder for `VARTANI_HOME`, free disk space, and press **Retry setup**.
- **Port already in use:** close the other program using the configured port, or change `PORT` in `%LOCALAPPDATA%\Vartani\.env`. If no custom port is set, Vartani can choose another free local port.
- **Browser did not open:** copy the `http://127.0.0.1:...` URL displayed in the launcher into Edge or Chrome.
- **More detail:** open `%LOCALAPPDATA%\Vartani\logs\launcher.log`.
- **Hosted model/network errors:** check internet access, API key, provider model name, and provider availability in the app’s model connection message.

## Packaged artifact checks

The build script tests profile-path selection, retry-safe setup, non-overwriting data import, missing-bundle errors, port-conflict behavior, core statistics, and bundled evidence. It then invokes the produced `Vartani.exe --smoke-test <log-file>` to verify frozen imports, API route handlers, bundled starter/evidence data, main UI, and speech page. This offline smoke check does not make hosted model calls. Actual server/browser startup, microphone input, Windows SmartScreen/signing, low-disk behavior, and upgrades should still be checked on a clean Windows machine.
