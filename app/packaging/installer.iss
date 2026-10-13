; Inno Setup script for the Windows installer. Build the app first
; (build_windows.ps1), then compile this with ISCC.exe.
; It installs for the current user only, so it never asks for administrator rights.

#define AppVersion "1.0.0"

[Setup]
AppId={{8C1B6E0A-5E0B-4D53-9C0C-7A6C2F9E4B11}
AppName=TradingAgents
AppVersion={#AppVersion}
AppVerName=TradingAgents {#AppVersion}
DefaultDirName={autopf}\TradingAgents
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\publish\Download
OutputBaseFilename=TradingAgents-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\TradingAgents.exe
UninstallDisplayName=TradingAgents
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "..\dist\TradingAgents\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; The app bundles the TradingAgents framework, whose license travels with it.
Source: "..\..\TradingAgents\LICENSE"; DestDir: "{app}"; DestName: "LICENSE-TradingAgents-framework.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\TradingAgents"; Filename: "{app}\TradingAgents.exe"
Name: "{autodesktop}\TradingAgents"; Filename: "{app}\TradingAgents.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TradingAgents.exe"; Description: "Start TradingAgents"; Flags: nowait postinstall skipifsilent
