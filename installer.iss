#include "release-assets\installer-config.iss"

[Setup]
AppId=MJH-editor
AppName=MJH-editor 梦江湖编辑器
AppVersion={#BuildVersion}
AppPublisher=zeroXlight
AppPublisherURL={#ReleasesURL}
DefaultDirName={localappdata}\Programs\MJH-editor
DefaultGroupName=MJH-editor
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
UsePreviousSetupType=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
AppMutex=MJH-editor-Desktop-v2
CloseApplications=no
RestartApplications=no
ArchiveExtraction=full
OutputDir=release-assets
OutputBaseFilename=MJH-editor-Setup
SetupIconFile=src\app.ico
UninstallDisplayIcon={app}\MJH-editor.exe
VersionInfoVersion={#BuildVersion}
Compression=lzma2/fast
WizardStyle=modern

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#ChineseLanguage}"

[Types]
Name: "typical"; Description: "标准安装"
Name: "custom"; Description: "自定义安装"; Flags: iscustom

[Components]
Name: "editor"; Description: "编辑器（必选）"; Types: typical custom; Flags: fixed
Name: "mobile"; Description: "手游模型和立绘（按需下载）"; ExtraDiskSpaceRequired: {#MobileSize}
Name: "source"; Description: "当前版本源码快照（按需下载）"; ExtraDiskSpaceRequired: {#SourceSize}

[Files]
Source: "release-assets\build\MJH-editor.exe"; DestDir: "{app}"; Flags: ignoreversion nocompression
Source: "release-assets\build\MJH-editor-Update.exe"; DestDir: "{app}"; Flags: ignoreversion nocompression
Source: "{srcexe}"; DestDir: "{app}\.update"; DestName: "installed-setup.exe"; Flags: external ignoreversion
Source: "升级使用说明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{src}\MJH-editor-MobileAssets.zip"; DestDir: "{app}"; Components: mobile; Check: NeedMobile and FileExists(ExpandConstant('{src}\MJH-editor-MobileAssets.zip')); ExternalSize: {#MobileSize}; Hash: "{#MobileHash}"; Flags: external extractarchive ignoreversion recursesubdirs createallsubdirs
Source: "{#MobileURL}"; DestName: "MJH-editor-MobileAssets.zip"; DestDir: "{app}"; Components: mobile; Check: NeedMobile and not FileExists(ExpandConstant('{src}\MJH-editor-MobileAssets.zip')); ExternalSize: {#MobileSize}; Hash: "{#MobileHash}"; Flags: external download extractarchive ignoreversion recursesubdirs createallsubdirs
Source: "{src}\MJH-editor-Source.zip"; DestDir: "{app}\source\{#BuildVersion}"; Components: source; Check: NeedSource and FileExists(ExpandConstant('{src}\MJH-editor-Source.zip')); ExternalSize: {#SourceSize}; Hash: "{#SourceHash}"; Flags: external extractarchive ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceURL}"; DestName: "MJH-editor-Source.zip"; DestDir: "{app}\source\{#BuildVersion}"; Components: source; Check: NeedSource and not FileExists(ExpandConstant('{src}\MJH-editor-Source.zip')); ExternalSize: {#SourceSize}; Hash: "{#SourceHash}"; Flags: external download extractarchive ignoreversion recursesubdirs createallsubdirs

[INI]
Filename: "{app}\installation.ini"; Section: "MJH-editor"; Key: "Managed"; String: "1"; Flags: uninsdeletesection
Filename: "{app}\installation.ini"; Section: "MJH-editor"; Key: "Version"; String: "{#BuildVersion}"

[Icons]
Name: "{group}\MJH-editor"; Filename: "{app}\MJH-editor.exe"; WorkingDir: "{app}"
Name: "{group}\MJH-editor 更新与修复"; Filename: "{app}\MJH-editor-Update.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\MJH-editor.exe"; Description: "启动 MJH-editor"; Flags: nowait postinstall skipifsilent

[Code]
function OpenProcess(Access: LongWord; InheritHandle: LongBool; ProcessId: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): LongBool;
  external 'CloseHandle@kernel32.dll stdcall';

function InitializeSetup(): Boolean;
var
  ProcessId: Integer;
  Process: THandle;
begin
  Result := True;
  ProcessId := StrToIntDef(ExpandConstant('{param:WAITPID|0}'), 0);
  if ProcessId > 0 then begin
    Process := OpenProcess($00100000, False, ProcessId);
    if Process <> 0 then begin
      Result := WaitForSingleObject(Process, 30000) = 0;
      CloseHandle(Process);
      if not Result then
        MsgBox('编辑器仍在关闭。请退出编辑器后重试。', mbError, MB_OK);
    end;
  end;
end;

function NeedMobile(): Boolean;
var
  Version: AnsiString;
begin
  Result := True;
  if not FileExists(ExpandConstant('{app}\mobile_assets\catalog.json')) then Exit;
  if not DirExists(ExpandConstant('{app}\mobile_assets\models')) then Exit;
  if not DirExists(ExpandConstant('{app}\mobile_assets\heads')) then Exit;
  if not DirExists(ExpandConstant('{app}\mobile_assets\portraits')) then Exit;
  if LoadStringFromFile(ExpandConstant('{app}\mobile_assets\.mjh-resource-version'), Version) then
    Result := Version <> '{#MobileVersion}';
end;

function NeedSource(): Boolean;
begin
  Result := not FileExists(ExpandConstant('{app}\source\{#BuildVersion}\src\desktop_app.py'));
end;
