; Inno Setup script for the Windows installer. Build from the repo root after
; PyInstaller and make_icons.py:
;   iscc /DAppVersion=0.1.0 packaging\windows\avilys.iss
; Output: dist\avilys-<version>-setup.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{9AB279E4-B180-4899-ABA0-CC9D31C556D6}
AppName=Avilys
AppVersion={#AppVersion}
AppVerName=Avilys {#AppVersion}
AppPublisher=Avilys
DefaultDirName={autopf}\Avilys
DefaultGroupName=Avilys
DisableProgramGroupPage=yes
; Installs for the current user without admin rights; the installer offers
; "all users" (with an admin prompt) as an option.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SourceDir=..\..
OutputDir=dist
OutputBaseFilename=avilys-{#AppVersion}-setup
SetupIconFile=packaging\build\avilys.ico
UninstallDisplayIcon={app}\avilys.exe
UninstallDisplayName=Avilys
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Close a running avilys before upgrading or uninstalling.
CloseApplications=yes
ChangesAssociations=yes
; English and Lithuanian: Setup uses the language of Windows, and asks only
; when Windows is in neither.
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
; Lithuanian isn't shipped with Inno Setup; this is its user-contributed
; translation (see Lithuanian.isl.LICENSE.txt).
Name: "lt"; MessagesFile: "packaging\windows\Lithuanian.isl"

[CustomMessages]
en.Associations=Associations:
en.OpenMagnets=Open magnet links with Avilys
en.OpenTorrents=Open .torrent files with Avilys
lt.Associations=Susiejimai:
lt.OpenMagnets=Magnet nuorodas atverti su Avilys
lt.OpenTorrents=.torrent failus atverti su Avilys

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "magnet"; Description: "{cm:OpenMagnets}"; GroupDescription: "{cm:Associations}"
Name: "torrentfiles"; Description: "{cm:OpenTorrents}"; GroupDescription: "{cm:Associations}"

[Files]
Source: "dist\avilys\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Avilys"; Filename: "{app}\avilys.exe"
Name: "{group}\{cm:UninstallProgram,Avilys}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Avilys"; Filename: "{app}\avilys.exe"; Tasks: desktopicon

[Registry]
; Always: register Avilys as a handler, so it is listed in Settings > Apps >
; Default apps even if the boxes below are unticked. Avilys can also do this
; itself from Settings > General > Default app.
Root: HKA; Subkey: "Software\Classes\Avilys.torrent"; ValueType: string; ValueName: ""; ValueData: "BitTorrent file"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Avilys.torrent\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\avilys.exe,0"
Root: HKA; Subkey: "Software\Classes\Avilys.torrent\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\avilys.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Avilys.magnet"; ValueType: string; ValueName: ""; ValueData: "URL:Magnet link"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Avilys.magnet"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Avilys.magnet\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\avilys.exe,0"
Root: HKA; Subkey: "Software\Classes\Avilys.magnet\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\avilys.exe"" ""%1"""
Root: HKA; Subkey: "Software\Avilys\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Avilys"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Avilys\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "A BitTorrent client"
Root: HKA; Subkey: "Software\Avilys\Capabilities\FileAssociations"; ValueType: string; ValueName: ".torrent"; ValueData: "Avilys.torrent"
Root: HKA; Subkey: "Software\Avilys\Capabilities\URLAssociations"; ValueType: string; ValueName: "magnet"; ValueData: "Avilys.magnet"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Avilys"; ValueData: "Software\Avilys\Capabilities"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.torrent\OpenWithProgids"; ValueType: string; ValueName: "Avilys.torrent"; ValueData: ""; Flags: uninsdeletevalue

; Ticked boxes: make Avilys the default. Only our own values are removed on
; uninstall, so another client that later claims these keeps working.
Root: HKA; Subkey: "Software\Classes\magnet"; ValueType: string; ValueName: ""; ValueData: "URL:Magnet link"; Flags: uninsdeletekeyifempty; Tasks: magnet
Root: HKA; Subkey: "Software\Classes\magnet"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletekeyifempty; Tasks: magnet
Root: HKA; Subkey: "Software\Classes\magnet\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\avilys.exe,0"; Flags: uninsdeletekey; Tasks: magnet
Root: HKA; Subkey: "Software\Classes\magnet\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\avilys.exe"" ""%1"""; Flags: uninsdeletekey; Tasks: magnet
Root: HKA; Subkey: "Software\Classes\.torrent"; ValueType: string; ValueName: ""; ValueData: "Avilys.torrent"; Flags: uninsdeletevalue; Tasks: torrentfiles

[Run]
Filename: "{app}\avilys.exe"; Description: "{cm:LaunchProgram,Avilys}"; Flags: nowait postinstall skipifsilent
