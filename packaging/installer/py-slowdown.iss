; py-slowdown, which plays audio slower or faster without changing its pitch.
; Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
;
; This program is free software: you can redistribute it and/or modify it
; under the terms of the GNU General Public License as published by the
; Free Software Foundation, either version 3 of the License, or (at your
; option) any later version. This program is distributed WITHOUT ANY
; WARRANTY; see the LICENSE.txt file, or <https://www.gnu.org/licenses/>.
;
; El instalador de py-slowdown para Windows, hecho con Inno Setup 6.
; tools/bundle-installer.py arma la carpeta SourceDir (python\, con
; py-slowdown dentro, py-slowdown.ico, LICENSE.txt) y corre ISCC con /D para
; cada valor:
;
;   ISCC /DAppVersion=0.2.0 /DFileVersion=0.2.0.0 /DSourceDir=... \
;        /DOutputDir=... /DOutputName=... /DAudio=mp3;m4a;... py-slowdown.iss
;
; Instala para el usuario (sin permisos de administrador) o para todos,
; según se elija al empezar (o /CURRENTUSER, /ALLUSERS). Silencioso:
; /VERYSILENT /SUPPRESSMSGBOXES [/TASKS="desktopicon"].

#ifndef AppVersion
  #error Give the version: ISCC /DAppVersion=... (tools/bundle-installer.py does)
#endif
#ifndef FileVersion
  #define FileVersion AppVersion + ".0.0"
#endif
#ifndef SourceDir
  #define SourceDir "image"
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputName
  #define OutputName "py-slowdown-" + AppVersion + "-windows-x64-setup"
#endif
#ifndef Audio
  #define Audio "mp3;m4a;flac;wav;ogg;opus"
#endif

#define ProgId "py-slowdown.audio"
; Los .slx, los ajustes de cada grabación: un tipo de py-slowdown, que los abre
#define SettingsProgId "py-slowdown.settings"

[Setup]
; (no cambiar nunca: así Windows reconoce las versiones como un programa)
AppId={{6F3B2C1E-8D4A-4B7E-9C55-2A1D0E7F4B93}
AppName=py-slowdown
AppVersion={#AppVersion}
AppVerName=py-slowdown {#AppVersion}
AppPublisher=Nicolas Vaughan
AppPublisherURL=https://github.com/nivaca/py-slowdown
AppSupportURL=https://github.com/nivaca/py-slowdown/issues
AppUpdatesURL=https://github.com/nivaca/py-slowdown/releases
AppContact=nicolasvaughan@proton.me
AppCopyright=Copyright (C) 2026 Nicolas Vaughan
AppComments=Plays audio slower or faster without changing its pitch. GPL-3.0-or-later.
VersionInfoVersion={#FileVersion}
VersionInfoDescription=py-slowdown setup
DefaultDirName={autopf}\py-slowdown
DefaultGroupName=py-slowdown
DisableProgramGroupPage=yes
LicenseFile={#SourceDir}\LICENSE.txt
; Per user by default; the first page offers to install for everyone
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#SourceDir}\py-slowdown.ico
UninstallDisplayIcon={app}\py-slowdown.ico
UninstallDisplayName=py-slowdown {#AppVersion}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.Comment=Play audio slower or faster without changing its pitch
spanish.Comment=Reproducir audio más lento o más rápido sin cambiar su altura
english.TaskOpenWith=Offer py-slowdown in "Open with" for audio files
spanish.TaskOpenWith=Ofrecer py-slowdown en «Abrir con» para los archivos de audio
english.GroupOther=Other tasks:
spanish.GroupOther=Otras tareas:
english.AudioFile=Audio file
spanish.AudioFile=Archivo de audio
english.SettingsFile=py-slowdown settings of a recording
spanish.SettingsFile=Ajustes de py-slowdown de una grabación

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "openwith"; Description: "{cm:TaskOpenWith}"; GroupDescription: "{cm:GroupOther}"

[InstallDelete]
; Lo de la versión anterior, para que no queden archivos que ya no son del
; programa (la configuración y los marcadores del usuario están en otra parte)
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\py-slowdown"; Filename: "{app}\python\pythonw.exe"; Parameters: "-s -m py_slowdown"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\py-slowdown.ico"; Comment: "{cm:Comment}"
Name: "{autodesktop}\py-slowdown"; Filename: "{app}\python\pythonw.exe"; Parameters: "-s -m py_slowdown"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\py-slowdown.ico"; Comment: "{cm:Comment}"; Tasks: desktopicon

[Registry]
; «Abrir con»: un tipo de archivo propio (sin quitarle a nadie su programa
; predeterminado), con el nombre y el ícono de py-slowdown
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "{cm:AudioFile}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\py-slowdown.ico"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "py-slowdown"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\python\pythonw.exe"" -s -m py_slowdown ""%1"""; Tasks: openwith
; Los .slx, siempre: su tipo, y py-slowdown en su «Abrir con» (y como su programa,
; si ninguno lo era ya: [Code])
Root: HKA; Subkey: "Software\Classes\{#SettingsProgId}"; ValueType: string; ValueData: "{cm:SettingsFile}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#SettingsProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\py-slowdown.ico"
Root: HKA; Subkey: "Software\Classes\{#SettingsProgId}\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "py-slowdown"
Root: HKA; Subkey: "Software\Classes\{#SettingsProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\python\pythonw.exe"" -s -m py_slowdown ""%1"""
Root: HKA; Subkey: "Software\Classes\.slx\OpenWithProgids"; ValueType: string; ValueName: "{#SettingsProgId}"; ValueData: ""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-s -m py_slowdown"; WorkingDir: "{%USERPROFILE}"; Description: "{cm:LaunchProgram,py-slowdown}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; (the bytecode Python writes while it runs, if it could)
Type: filesandordirs; Name: "{app}\python"
Type: dirifempty; Name: "{app}"

[Code]
{ Las extensiones de audio, en «Abrir con»: un valor con el tipo propio en
  OpenWithProgids de cada una, que se quita al desinstalar }
function Extensions: TArrayOfString;
var
  List: String;
  Count, P: Integer;
begin
  List := '{#Audio}' + ';';
  Count := 0;
  SetArrayLength(Result, 0);
  while Length(List) > 0 do
  begin
    P := Pos(';', List);
    if P > 1 then
    begin
      SetArrayLength(Result, Count + 1);
      Result[Count] := Copy(List, 1, P - 1);
      Count := Count + 1;
    end;
    Delete(List, 1, P);
  end;
end;

function ClassesRoot: Integer;
begin
  if IsAdminInstallMode then
    Result := HKEY_LOCAL_MACHINE
  else
    Result := HKEY_CURRENT_USER;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Names: TArrayOfString;
  I: Integer;
  Current: String;
begin
  { .slx: py-slowdown es su programa, a menos que otro ya lo fuera (los modelos
    de Simulink también terminan en .slx) }
  if CurStep = ssPostInstall then
    if not RegQueryStringValue(HKEY_CLASSES_ROOT, '.slx', '', Current) or (Current = '') then
      RegWriteStringValue(ClassesRoot, 'Software\Classes\.slx', '', '{#SettingsProgId}');
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('openwith') then
  begin
    Names := Extensions;
    for I := 0 to GetArrayLength(Names) - 1 do
      RegWriteStringValue(ClassesRoot, 'Software\Classes\.' + Names[I] + '\OpenWithProgids', '{#ProgId}', '');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Names: TArrayOfString;
  I: Integer;
  Current: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { (el programa de los .slx se quita solo si es py-slowdown) }
    if RegQueryStringValue(ClassesRoot, 'Software\Classes\.slx', '', Current) and (Current = '{#SettingsProgId}') then
      RegDeleteValue(ClassesRoot, 'Software\Classes\.slx', '');
    Names := Extensions;
    for I := 0 to GetArrayLength(Names) - 1 do
      RegDeleteValue(ClassesRoot, 'Software\Classes\.' + Names[I] + '\OpenWithProgids', '{#ProgId}');
  end;
end;
