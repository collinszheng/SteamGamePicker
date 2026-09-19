; Steam 游戏抽签器 安装包脚本（T7.2，对应 PRD 7.1 ~ 7.3）
;
; 编译（在项目根目录执行）：
;   ISCC.exe packaging\installer.iss      （ISCC 位于 Inno Setup 安装目录）
; 产物：dist\SteamGamePicker_Setup.exe
;
; 特性：
;   * 非管理员权限即可安装（PrivilegesRequired=lowest，装到用户目录）
;   * 仅 64 位系统
;   * 桌面快捷方式可选、开始菜单项、安装完成后可选立即运行
;   * 支持静默安装（Inno 原生 /VERYSILENT）
;   * 卸载时询问是否同时删除配置与缓存，默认保留（PRD 6.5）

#define AppName "Steam 游戏抽签器"
#define AppNameEn "SteamGamePicker"
#define AppVersion "1.0.0"
#define AppPublisher "Steam 游戏抽签器项目"
#define AppExeName "SteamGamePicker.exe"
#define SourceExe "..\dist\SteamGamePicker.exe"
#define IconFile "..\assets\app.ico"

[Setup]
AppId={{7C2E5F1A-3B4D-4E6F-9A10-5D8C7B6A4E32}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppNameEn}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=SteamGamePicker_Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
; 若脚本目录下存在官方中文语言包则用中文，否则退回自带英文（不影响应用本身的中文界面）
#if FileExists(AddBackslash(SourcePath) + "ChineseSimplified.isl")
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
{ PRD 6.5：卸载时询问是否同时删除配置与缓存，默认「否」（保留）。
  静默卸载（/VERYSILENT）下不弹窗，直接保留数据，避免自动化部署卡住。 }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if UninstallSilent then
      Exit;
    DataDir := ExpandConstant('{userappdata}\SteamGamePicker');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否同时删除配置与缓存？' + #13#10 + DataDir + #13#10 +
                '选择「否」将保留，重新安装后设置会自动恢复。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
