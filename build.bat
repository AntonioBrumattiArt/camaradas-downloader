@echo off
rem Gera o Camaradas-Downloader.zip para WINDOWS (instalador + LEIA-ME) do zero.
rem Para Mac, use o build_mac.sh num Mac ou o GitHub Actions (veja o README).
rem Requisitos: Python 3.12+, Inno Setup 6 e vendor\ffmpeg.exe, ffprobe.exe, deno.exe
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo [1/7] Criando ambiente Python...
  py -3 -m venv .venv || goto :erro
)
set PY=.venv\Scripts\python.exe

echo [2/7] Instalando dependencias...
%PY% -m pip install -q -r requirements.txt || goto :erro

echo [3/7] Gerando sons e icones...
%PY% make_assets.py || goto :erro

echo [4/7] Rodando testes...
%PY% -m pytest -q tests || goto :erro

for %%F in (ffmpeg.exe ffprobe.exe deno.exe) do (
  if not exist vendor\%%F (
    echo Falta vendor\%%F. Veja o README.md.
    goto :erro
  )
)

echo [5/7] Empacotando com PyInstaller...
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name CamaradasDownloader --icon assets\icon.ico ^
  --add-data "ui;ui" --add-data "assets;assets" --add-data "vendor;vendor" ^
  app.py || goto :erro

echo [6/7] Gerando instalador com Inno Setup...
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup 6 nao encontrado. Instale com: winget install JRSoftware.InnoSetup
  goto :erro
)
"%ISCC%" /Q installer.iss || goto :erro

echo [7/7] Montando Camaradas-Downloader.zip...
if exist Camaradas-Downloader.zip del /q Camaradas-Downloader.zip
powershell -NoProfile -Command "Compress-Archive -LiteralPath 'dist\CamaradasDownloader-Setup.exe','LEIA-ME, CAMARADA.txt' -DestinationPath 'Camaradas-Downloader.zip' -CompressionLevel Optimal" || goto :erro

echo.
echo Pronto! Camaradas-Downloader.zip gerado.
exit /b 0

:erro
echo.
echo Falhou. Veja a mensagem acima.
exit /b 1
