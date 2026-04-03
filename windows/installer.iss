; ── ReBook for Windows — Inno Setup Script ───────────────────────────────────
; Builds a professional Setup.exe installer
; Usage: iscc installer.iss
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)

#define MyAppName "ReBook"
#define MyAppVersion "2.2.1"
#define MyAppPublisher "ReBook"
#define MyAppURL "https://github.com/realtek1990/rebook"
#define MyAppExeName "ReBook.exe"

[Setup]
AppId={{7F2A9E1B-4C3D-4E5F-8A6B-9C0D1E2F3A4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output
OutputDir=output
OutputBaseFilename=ReBook-Setup-{#MyAppVersion}
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Visual
SetupIconFile=icon.ico
WizardStyle=modern
WizardSizePercent=110
; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Misc
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "finnish"; MessagesFile: "compiler:Languages\Finnish.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "romanian"; MessagesFile: "compiler:Languages\Romanian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable (built by GitHub Actions / PyInstaller)
Source: "dist\ReBook.exe"; DestDir: "{app}"; Flags: ignoreversion
; Python backend (shared with macOS via build_win_dist.sh)
Source: "dist\rebook_win.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\i18n.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\converter.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\corrector.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\image_translator.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\manual_convert.py"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Check Python installed, warn if missing
function InitializeSetup(): Boolean;
var
  PythonPath: String;
begin
  Result := True;
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SOFTWARE\Python\PythonCore\3.12\InstallPath',
    '', PythonPath) and
     not RegQueryStringValue(HKEY_CURRENT_USER,
    'SOFTWARE\Python\PythonCore\3.12\InstallPath',
    '', PythonPath) then
  begin
    MsgBox('ReBook requires Python 3.10 or newer.' + #13#10 +
           'Please install Python from https://python.org and try again.' + #13#10#13#10 +
           'The app will still work if Python is installed system-wide.', mbInformation, MB_OK);
  end;
end;
