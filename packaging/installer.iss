[Setup]
AppId=MAJIMeeting
AppName=MAJIMeeting
AppVersion=0.2.8
AppPublisher=MAJIMeeting
DefaultDirName={localappdata}\Programs\MAJIMeeting
DefaultGroupName=MAJIMeeting
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=MAJIMeeting-0.2.8-preview-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\MAJIMeeting.exe

[Files]
Source: "..\dist\MAJIMeeting\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "..\scripts\setup-diarization.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MAJIMeeting"; Filename: "{app}\MAJIMeeting.exe"
Name: "{userdesktop}\MAJIMeeting"; Filename: "{app}\MAJIMeeting.exe"; Tasks: desktopicon

Name: "{group}\Préparer la diarisation locale"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoExit -ExecutionPolicy Bypass -File ""{app}\setup-diarization.ps1"""; WorkingDir: "{app}"

[Tasks]
Name: desktopicon; Description: "Créer un raccourci sur le bureau"; Flags: unchecked
