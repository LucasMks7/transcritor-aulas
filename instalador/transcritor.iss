; Receita do Inno Setup. Use scripts/montar_instalador.py, que passa Versao, Origem e Saida.

#define Nome "Transcritor de Aulas"

[Setup]
; Identifica o programa nas atualizações. Nunca pode mudar.
AppId={{8EEB4DF6-D90E-4219-BD1C-B02808630D5E}
AppName={#Nome}
AppVersion={#Versao}
AppPublisher=Lucas Marques de Assis
AppPublisherURL=https://github.com/LucasMks7/transcritor-aulas
DefaultDirName={autopf}\{#Nome}
DisableProgramGroupPage=yes
; Instala só para a pessoa: não pede a senha de administrador.
PrivilegesRequired=lowest
; As bibliotecas de transcrição só existem para Windows de 64 bits.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Saida}
OutputBaseFilename=transcritor-aulas-{#Versao}-instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Transcritor.exe

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktop"; Description: "{cm:CreateDesktopIcon}"

[InstallDelete]
; Uma atualização não pode deixar bibliotecas da versão anterior misturadas às novas.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origem}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#Nome}"; Filename: "{app}\Transcritor.exe"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\Transcritor.exe"; Tasks: desktop

[Run]
Filename: "{app}\Transcritor.exe"; Description: "{cm:LaunchProgram,{#Nome}}"; Flags: nowait postinstall skipifsilent

[Code]
// As preferências e a autorização do Google são da pessoa: só saem se ela pedir.
// Na desinstalação silenciosa ninguém responde, e elas ficam.
procedure CurUninstallStepChanged(Etapa: TUninstallStep);
var
  Pasta: String;
begin
  Pasta := ExpandConstant('{userappdata}\transcritor-aulas');
  if (Etapa = usPostUninstall) and DirExists(Pasta) and not UninstallSilent then
    if MsgBox('Apagar também as preferências e a autorização do Google Drive guardadas neste computador?'
      + #13#10#13#10 + 'Suas transcrições, seus áudios e os arquivos no Drive não são apagados.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DeleteFile(Pasta + '\token.json');
      DeleteFile(Pasta + '\preferencias.json');
      RemoveDir(Pasta);
    end;
end;
