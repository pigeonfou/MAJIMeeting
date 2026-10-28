[Setup]
AppId=MAJIMeeting-Flash-Experimental
AppName=MAJIMeeting Flash expérimental
AppVersion=0.2.6
AppPublisher=MAJIMeeting
DefaultDirName={localappdata}\Programs\MAJIMeeting-Flash
DefaultGroupName=MAJIMeeting Flash expérimental
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=MAJIMeeting-0.2.6-Flash-Experimental-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\MAJIMeeting-Flash.exe

[Files]
Source: "..\..\dist\MAJIMeeting-Flash\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MAJIMeeting Flash expérimental"; Filename: "{app}\MAJIMeeting-Flash.exe"
