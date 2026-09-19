; Steam Game Picker 安装包脚本（T7.2，对应 PRD 7.1 ~ 7.3）
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
;   * 覆盖升级保留安装目录与用户配置；应用更名（1.0.1）后自动清理旧名的快捷方式

#define AppName "Steam Game Picker"
; 目录名与可执行文件名保持 ASCII 不变（改名不影响已安装路径与用户配置）
#define AppNameEn "SteamGamePicker"
#define AppVersion "1.0.1"
#define AppPublisher "Steam Game Picker"
#define AppExeName "SteamGamePicker.exe"
#define SourceExe "..\dist\SteamGamePicker.exe"
#define IconFile "..\assets\app.ico"
; 1.0.0 及更早版本用的显示名：升级时要把它留下的开始菜单目录 /
; 桌面快捷方式清掉，否则用户会同时看到新旧两套快捷方式（实测确实会残留）
#define LegacyAppName "Steam 游戏抽签器"

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
; 保留上次的安装目录，但开始菜单目录必须换成新名字（默认会沿用旧目录）
UsePreviousAppDir=yes
UsePreviousGroup=no
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
; 不带 checkedonce：更名后旧名的桌面快捷方式会被删掉，
; 若这里沿用"升级时默认不勾"，老用户升级后桌面上就什么都不剩了
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[InstallDelete]
; 更名前的旧快捷方式（PRD D11 / AC-56）
Type: filesandordirs; Name: "{userprograms}\{#LegacyAppName}"
Type: files; Name: "{autodesktop}\{#LegacyAppName}.lnk"

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
