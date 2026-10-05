; Inno Setup script for ReyOS Browser on Windows.
; Build after PyInstaller:  iscc /DAppVersion=0.1.0.102 windows\reyos-browser.iss
; Per-user install (no admin prompt), like most browsers' user installs.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{7C1B0E52-4F0B-4E1C-9C2E-5E8B2A9D6F31}
AppName=ReyOS Browser
AppVersion={#AppVersion}
AppPublisher=ReyApps
AppPublisherURL=https://reyos.reyapps.com
DefaultDirName={localappdata}\Programs\ReyOS Browser
DefaultGroupName=ReyOS Browser
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ReyOSBrowser-Setup-{#AppVersion}
SetupIconFile=..\files\usr\share\reyos\browser\assets\reyos-browser.ico
UninstallDisplayIcon={app}\ReyOSBrowser.exe
LicenseFile=..\..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\ReyOSBrowser\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\ReyOS Browser"; Filename: "{app}\ReyOSBrowser.exe"; AppUserModelID: "ReyOS.Browser"
Name: "{userdesktop}\ReyOS Browser"; Filename: "{app}\ReyOSBrowser.exe"; AppUserModelID: "ReyOS.Browser"; Tasks: desktopicon

[Run]
Filename: "{app}\ReyOSBrowser.exe"; Description: "Start ReyOS Browser"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Shortcuts for installed web apps point at this exe, so they go with it.
; Bookmarks, shortcuts and settings in %APPDATA%\ReyOS Browser are kept.
Type: filesandordirs; Name: "{userprograms}\ReyOS Web Apps"
Type: filesandordirs; Name: "{userappdata}\ReyOS Browser\webapps"
