[Setup]
AppId=MAJIMeeting
AppName=MAJIMeeting
AppVersion=0.2.0
AppPublisher=MAJIMeeting
DefaultDirName={localappdata}\Programs\MAJIMeeting
DefaultGroupName=MAJIMeeting
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=MAJIMeeting-0.2.0-preview-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\MAJIMeeting.exe

[Files]
Source: "..\dist\MAJIMeeting\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MAJIMeeting"; Filename: "{app}\MAJIMeeting.exe"
Name: "{userdesktop}\MAJIMeeting"; Filename: "{app}\MAJIMeeting.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Créer un raccourci sur le bureau"; Flags: unchecked
