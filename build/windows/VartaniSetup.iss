#define AppVersion "1.1.0"
[Setup]
AppId={{A688DBB9-773F-4947-947E-6B67663E0FB7}
AppName=Vartani
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Vartani
DefaultGroupName=Vartani
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputFolder}
OutputBaseFilename=VartaniSetup-x64
UninstallDisplayIcon={app}\Vartani.exe
Compression=lzma2
SolidCompression=yes
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
AppMutex=Local\VartaniDesktopInstallerGuard

[Files]
Source: "{#PayloadFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vartani"; Filename: "{app}\Vartani.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\Vartani.exe"; Description: "Open Vartani"; Flags: nowait postinstall skipifsilent

[Code]
const
  RuntimeKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function ValidWebViewVersion(Root: Integer): Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(Root, RuntimeKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup(): Boolean;
begin
  Result := ValidWebViewVersion(HKLM32) or ValidWebViewVersion(HKLM64) or ValidWebViewVersion(HKCU32) or ValidWebViewVersion(HKCU64);
  if not Result then
    SuppressibleMsgBox('Vartani needs the Microsoft Edge WebView2 Runtime. Install the Evergreen Runtime from https://developer.microsoft.com/microsoft-edge/webview2/ and run Setup again.', mbError, MB_OK, IDOK);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  AppPath, ProfilePath: String;
begin
  Result := '';
  AppPath := AddBackslash(ExpandConstant('{app}'));
  ProfilePath := AddBackslash(ExpandConstant('{localappdata}\Vartani'));
  if (CompareText(Copy(AppPath, 1, Length(ProfilePath)), ProfilePath) = 0) or
     (CompareText(Copy(ProfilePath, 1, Length(AppPath)), AppPath) = 0) then
    Result := 'Choose a different install folder. Vartani keeps saved settings and runs separately from its installed files.';
end;
