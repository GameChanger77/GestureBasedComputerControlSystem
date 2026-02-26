[Setup]
AppName=gbccs
AppVersion=1.0.0
DefaultDirName={pf}\gbccs
DefaultGroupName=gbccs
SetupIconFile={#SourcePath}\..\..\icons\gbccs_icon.ico
OutputDir=installer_out
OutputBaseFilename=gbccsSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "{#SourcePath}\..\..\dist\gbccs\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\gbccs"; Filename: "{app}\gbccs.exe"; IconFilename: "{app}\gbccs.exe"
Name: "{autodesktop}\gbccs"; Filename: "{app}\gbccs.exe"; IconFilename: "{app}\gbccs.exe"

[Run]
Filename: "{app}\gbccs.exe"; Description: "Launch GBCCS"; Flags: nowait postinstall skipifsilent