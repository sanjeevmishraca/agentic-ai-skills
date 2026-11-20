; Inno Setup script — builds VanyajeevSetup-<version>.exe from dist\Vanyajeev
#define AppVersion GetEnv("VANYAJEEV_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B7E3C2A-9D41-4F7B-A1E2-5C8D0F3B7A61}
AppName=Vanyajeev
AppVersion={#AppVersion}
AppPublisher=Sanjeev Mishra
AppPublisherURL=https://github.com/sanjeevmishraca/agentic-ai-skills
DefaultDirName={autopf}\Vanyajeev
DefaultGroupName=Vanyajeev
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=VanyajeevSetup-{#AppVersion}
SetupIconFile=..\vanyajeev\assets\icon.ico
UninstallDisplayIcon={app}\Vanyajeev.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Vanyajeev\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vanyajeev"; Filename: "{app}\Vanyajeev.exe"
Name: "{autodesktop}\Vanyajeev"; Filename: "{app}\Vanyajeev.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Vanyajeev.exe"; Description: "Launch Vanyajeev"; Flags: nowait postinstall skipifsilent
