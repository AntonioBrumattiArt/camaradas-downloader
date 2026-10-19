; Instalador do Camaradas Downloader para Windows (Inno Setup 6)
; Compile com: ISCC.exe installer.iss   (o build.bat já faz isso)
; A versão abaixo também é lida pelo build_mac.sh.

#define AppName "Camaradas Downloader"
#define AppVersion "1.1.0"
#define AppExe "CamaradasDownloader.exe"

[Setup]
AppId={{6E4C2B1A-9F3D-4D57-8C1E-CA3A7AD0F917}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Camaradas
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=CamaradasDownloader-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\CamaradasDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; yt-dlp baixado e configurações
Type: filesandordirs; Name: "{localappdata}\CamaradasDownloader"

[Code]
const
  WebView2Key = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2Url = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';

var
  DownloadPage: TDownloadWizardPage;

function HasVersion(Root: Integer; Key: String): Boolean;
var
  V: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
end;

{ O runtime do WebView2 vem no Windows 11 e na maioria dos Windows 10 atualizados }
function WebView2Installed: Boolean;
begin
  Result := HasVersion(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
    or HasVersion(HKLM, WebView2Key)
    or HasVersion(HKCU, WebView2Key);
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), 'Baixando o WebView2 da Microsoft...', nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if (CurPageID = wpReady) and not WebView2Installed then
  begin
    { Bootstrapper oficial da Microsoft (Evergreen) }
    DownloadPage.Clear;
    DownloadPage.Add(WebView2Url, 'MicrosoftEdgeWebview2Setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '',
          SW_SHOW, ewWaitUntilTerminated, ResultCode);
      except
        MsgBox('Não consegui baixar o WebView2 da Microsoft, que o app precisa para abrir.' + #13#10 +
          'Instale manualmente: procure "WebView2 Runtime" no site da Microsoft e depois abra o app.',
          mbInformation, MB_OK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
