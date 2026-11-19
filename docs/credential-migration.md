# Prompt 3 handoff: credentials and regression tests

Merge `security-tests` from the integrated baseline `6b8212a`. The branch includes the rebuilt browser bundle. If either working branch changed browser source, resolve source files first, then rebuild `web/` with `npm ci` and `npm run build` from `frontend/`. Do not hand-merge generated JavaScript. Run `npm test` and `python -m pytest -q tests` in the merged tree using the project's locked Python environment.

## What an upgrade does

On Windows, `data/user/models.json` still holds connection settings. API keys and Hugging Face read tokens are stored in that file only as Windows DPAPI encrypted blobs. They can normally be reopened with the same Windows sign-in on the same computer. No plaintext fallback is used. The UI gets only a yes/no indicator for each saved credential.

Startup upgrades older entries in one file replacement and cleans credential fields and known echoes out of old run metadata. The launcher’s import also cleans the destination copy before writing it; it leaves the original folder and its existing files alone. If old credential migration fails, the app stays open and the model picker reports the problem. The original settings are preserved and can be retried. Blank credential fields preserve the current value; **Remove saved API key/token** and **Save changes** clear it. If the profile is moved to another Windows user or PC, edit each affected model and re-enter its credential. Previous backups and already downloaded exports are outside the migration.

## Packaged Windows smoke test

Use an isolated directory in `%TEMP%` and dummy credentials throughout. Do not run the check against the user's existing Vartani profile or sign in to real providers.

1. Start the loopback mock provider from the merged source: `python tests/mock_provider.py --port 8766`. A packaged `python.exe` can also run this script. The provider accepts `vartani-demo-key` for model `requires-dummy-auth`; a missing or wrong key returns HTTP 401. Use a different port if 8766 is in use and update the URL below.
2. In a separate PowerShell terminal, set a temporary profile and seed an old connection. `VARTANI_HOME` and `VARTANI_DATA` are process environment settings; launch the new package from this same terminal so it inherits them.

   ```powershell
   $env:VARTANI_HOME = Join-Path $env:TEMP ("vartani-package-test-" + [guid]::NewGuid().ToString('N'))
   $env:VARTANI_DATA = Join-Path $env:VARTANI_HOME 'data'
   $modelsFile = Join-Path $env:VARTANI_DATA 'user\models.json'
   New-Item -ItemType Directory -Force -Path (Split-Path -Parent $modelsFile) | Out-Null
   @'
   [
     {"id":"probe","label":"Credential migration probe","kind":"openai","base_url":"http://127.0.0.1:8766/v1","model":"requires-dummy-auth","needs_key":true,"api_key":"vartani-demo-key"},
     {"id":"dummy-hf","label":"Dummy HF token","kind":"hf","hf_id":"placeholder/model","hf_token":"hf_vartani_dummy"}
   ]
   '@ | Set-Content -LiteralPath $modelsFile -Encoding utf8
   ```

3. Launch the installed `Vartani.exe`. Open **Test Lab** and use **select & test** on the migration probe. It should connect and run a starter dataset. Inspect the temporary `models.json`: neither dummy value nor the old plaintext credential fields should remain. The file should show an encrypted value for each model. Verify the models API and CSV, JSONL, and HTML run exports contain neither dummy value nor the encrypted blobs.
4. Exit Vartani fully and restart it with the same temporary environment. The probe must connect again. Edit the name with a blank key field and save; it should still connect. Replace the key with an incorrect dummy value and check for a useful HTTP 401 message. Restore the expected key and check that it connects. Clear the saved key and check that the app asks for a new one. Delete the Hugging Face model and verify its encrypted token entry disappears. Do not test that dummy HF connection against the internet.
5. In a second temporary profile, corrupt only the probe's encrypted value while the app is shut down. The model should still be listed after restart. Selecting it should ask the user to re-enter the key; editing and replacing the unreadable value should restore the connection. If a second Windows account is available, copying the temporary profile into that account and then replacing the key there exercises actual account isolation as well.
6. Separately try **Import old Vartani data** using a temporary legacy source and a fresh temporary destination. Verify the source stays byte for byte unchanged and the destination stores the protected key. For a migration write failure, give the app a temporary profile whose `models.json` it can read but cannot replace. Check for the recovery message and the unchanged original file, then restore access and retry.

The automated suite uses temporary profiles, dummy credentials, the mock provider, and a mocked Hugging Face connection. It does not authenticate with real providers or install local model/speech packages. The package smoke test and a second real Windows account are separate checks.
