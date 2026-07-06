; Inno Setup — Табель (лёгкая, без «Проезда»). UTF-8 (BOM добавляется перед компиляцией).
; Версию можно переопределить при компиляции: ISCC.exe /DAppVer=1.3.0 lite.iss
#ifndef AppVer
  #define AppVer "1.3.0"
#endif
#define SrcDir "C:\Users\User\tabel_pkg\lite"
#define OutDir "C:\Users\User\tabel_pkg\out"

[Setup]
AppId={{7F3A2C10-9B4D-4E61-AE12-1F2D3C4B5A61}
AppName=Табель (без проезда)
AppVersion={#AppVer}
AppPublisher=Станислав
DefaultDirName={localappdata}\Tabel-lite
DefaultGroupName=Табель (без проезда)
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename=Табель_без_проезда_setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; --- обновление поверх существующей установки (не вторая копия) ---
UsePreviousAppDir=yes
DisableDirPage=yes
CloseApplications=yes
RestartApplications=no
AppMutex=TabelAppRunningMutex

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SrcDir}\Tabel.exe"; DestDir: "{app}"; DestName: "Табель.exe"; Flags: ignoreversion
Source: "{#SrcDir}\instruction.txt"; DestDir: "{app}"; DestName: "Инструкция.txt"; Flags: ignoreversion
Source: "{#SrcDir}\data\*"; DestDir: "{app}\data"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Табель (без проезда)"; Filename: "{app}\Табель.exe"
Name: "{group}\Инструкция"; Filename: "{app}\Инструкция.txt"
Name: "{group}\Удалить"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Табель (без проезда)"; Filename: "{app}\Табель.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Табель.exe"; Description: "Запустить Табель"; Flags: nowait postinstall skipifsilent

