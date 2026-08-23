#define AppName "Back in my days Youtube"
#define AppVersion "0.1.1"
#define AppExeName "Back in my days Youtube.exe"

[Setup]
AppId={{1D6D2C15-7D4C-46B9-B68D-3B3991FA717A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Rasslabsya4el
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourcePath}\..\app\assets\icons\back-in-my-days-youtube.ico
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir={#SourcePath}\..\dist
OutputBaseFilename=Back in my days Youtube Setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Dirs]
Name: "{commonappdata}\Back in my days Youtube"; Permissions: users-modify
Name: "{commonappdata}\Back in my days Youtube\logs"; Permissions: users-modify

[Files]
Source: "{#SourcePath}\..\dist\Back in my days Youtube Installer Payload\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function InstallerDebugLogPath(): string;
begin
  Result := ExpandConstant('{commonappdata}\Back in my days Youtube\logs\debug.log');
end;

procedure AppendInstallerDebugLog(const Message: string);
var
  LogLine: string;
begin
  ForceDirectories(ExtractFileDir(InstallerDebugLogPath()));
  LogLine :=
    '[' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + '] [installer] ' + Message + #13#10;
  SaveStringToFile(InstallerDebugLogPath(), LogLine, True);
  Log(Message);
end;

procedure WriteInstallerSupportFiles();
var
  PointerPath: string;
  MarkerPath: string;
begin
  PointerPath := ExpandConstant('{app}\debug-log-path.txt');
  MarkerPath := ExpandConstant('{app}\install-mode.txt');

  SaveStringToFile(PointerPath, InstallerDebugLogPath() + #13#10, False);
  SaveStringToFile(MarkerPath, 'installed' + #13#10, False);

  AppendInstallerDebugLog('Wrote support files: ' + PointerPath + ', ' + MarkerPath);
end;

function InitializeSetup(): Boolean;
begin
  AppendInstallerDebugLog('=== setup session start ===');
  Result := True;
end;

procedure InitializeWizard();
begin
  AppendInstallerDebugLog('Wizard initialized.');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
    AppendInstallerDebugLog('Ready to install. TargetDir=' + WizardDirValue());
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppExePath: string;
  BundledRuntimePath: string;
begin
  if CurStep = ssInstall then
  begin
    AppendInstallerDebugLog('File copy/install step started.');
  end;

  if CurStep = ssPostInstall then
  begin
    WriteInstallerSupportFiles();
    AppExePath := ExpandConstant('{app}\{#AppExeName}');
    BundledRuntimePath := ExpandConstant('{app}\_internal\webview2-fixed-runtime\msedgewebview2.exe');
    AppendInstallerDebugLog(
      'Post-install verification AppExeExists=' + IntToStr(Ord(FileExists(AppExePath))) +
      ' BundledWebView2Exists=' + IntToStr(Ord(FileExists(BundledRuntimePath))) +
      ' AppExePath=' + AppExePath +
      ' BundledWebView2Path=' + BundledRuntimePath
    );
  end;

  if CurStep = ssDone then
    AppendInstallerDebugLog('Setup finished.');
end;
