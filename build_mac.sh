#!/usr/bin/env bash
# Gera o Camaradas Downloader para Mac: .app, .dmg e o zip para os amigos.
# Rode NUM MAC (ou deixe o GitHub Actions rodar, veja .github/workflows/build-mac.yml):
#     bash build_mac.sh
# Gera para a arquitetura do Mac onde roda: arm64 (Apple Silicon, M1/M2/M3...) ou x86_64 (Intel).
# Requisitos: macOS 11+, Python 3.10+ (python3), internet. Nada de Xcode.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Este script só roda no macOS. No Windows use o build.bat." >&2
  exit 1
fi

APP_NAME="Camaradas Downloader"
BUNDLE_ID="com.camaradas.downloader"
VERSION="$(grep -m1 '#define AppVersion' installer.iss | cut -d'"' -f2)"
ARCH="$(uname -m)"                        # arm64 ou x86_64
case "$ARCH" in
  arm64)  DENO_ARCH="aarch64"; FF_ARCH="arm64"; LABEL="AppleSilicon" ;;
  x86_64) DENO_ARCH="x86_64";  FF_ARCH="amd64"; LABEL="Intel" ;;
  *) echo "Arquitetura não suportada: $ARCH" >&2; exit 1 ;;
esac
PY="${PYTHON:-python3}"
VENDOR="vendor_mac/$ARCH"

echo "== Camaradas Downloader $VERSION para Mac ($LABEL) =="

echo "[1/8] Ambiente Python..."
if [ ! -x .venv-mac/bin/python ]; then
  "$PY" -m venv .venv-mac
fi
VPY=.venv-mac/bin/python
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r requirements.txt

echo "[2/8] Sons e ícones..."
"$VPY" make_assets.py

echo "[3/8] Testes..."
"$VPY" -m pytest -q tests

# Baixa com algumas tentativas (o servidor do ffmpeg às vezes oscila)
baixar() {  # baixar URL DESTINO
  local n
  for n in 1 2 3 4 5; do
    if curl -fsSL --retry 3 -o "$2" "$1"; then return 0; fi
    echo "   tentativa $n falhou, tentando de novo..." >&2
    sleep 3
  done
  return 1
}

echo "[4/8] ffmpeg, ffprobe e deno para $ARCH..."
mkdir -p "$VENDOR"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT

if [ ! -x "$VENDOR/deno" ]; then
  Z="deno-$DENO_ARCH-apple-darwin.zip"
  baixar "https://github.com/denoland/deno/releases/latest/download/$Z" "$TMPD/$Z"
  baixar "https://github.com/denoland/deno/releases/latest/download/$Z.sha256sum" "$TMPD/$Z.sha256sum"
  ESPERADO="$(awk '{print $1}' "$TMPD/$Z.sha256sum" | tr 'A-F' 'a-f')"
  OBTIDO="$(shasum -a 256 "$TMPD/$Z" | awk '{print $1}')"
  if [ "$ESPERADO" != "$OBTIDO" ]; then echo "SHA-256 do deno não confere" >&2; exit 1; fi
  unzip -q -o "$TMPD/$Z" -d "$TMPD/deno"
  cp "$TMPD/deno/deno" "$VENDOR/deno"
fi

# Builds estáticos do FFmpeg para macOS de ffmpeg.martin-riedl.de (assinados pelo autor).
# Tenta a versão "release"; se o servidor não tiver, usa a "snapshot".
for TOOL in ffmpeg ffprobe; do
  if [ -x "$VENDOR/$TOOL" ]; then continue; fi
  OKFF=0
  for KIND in release snapshot; do
    URL="https://ffmpeg.martin-riedl.de/redirect/latest/macos/$FF_ARCH/$KIND/$TOOL.zip"
    if baixar "$URL" "$TMPD/$TOOL.zip" && unzip -q -o "$TMPD/$TOOL.zip" -d "$TMPD/$TOOL"; then
      OKFF=1; break
    fi
  done
  if [ "$OKFF" != 1 ]; then echo "Não consegui baixar o $TOOL para macOS" >&2; exit 1; fi
  ACHADO=""
  while IFS= read -r f; do ACHADO="$f"; break; done < <(find "$TMPD/$TOOL" -type f -name "$TOOL")
  if [ -z "$ACHADO" ]; then echo "O zip do $TOOL veio sem o executável" >&2; exit 1; fi
  cp "$ACHADO" "$VENDOR/$TOOL"
done

chmod +x "$VENDOR/ffmpeg" "$VENDOR/ffprobe" "$VENDOR/deno"
xattr -c "$VENDOR/ffmpeg" "$VENDOR/ffprobe" "$VENDOR/deno" 2>/dev/null || true
cp vendor/FFMPEG-LICENSE.txt "$VENDOR/FFMPEG-LICENSE.txt" 2>/dev/null || true
for B in ffmpeg ffprobe deno; do
  INFO="$(file "$VENDOR/$B")"
  case "$INFO" in *"$ARCH"*) ;; *) echo "$B não é $ARCH: $INFO" >&2; exit 1 ;; esac
  # roda de verdade (falha aqui se o binário não executar neste Mac)
  if [ "$B" = deno ]; then V="$("$VENDOR/$B" --version)"; else V="$("$VENDOR/$B" -hide_banner -version)"; fi
  echo "   ${V%%$'\n'*}"
done

echo "[5/8] Empacotando o .app com PyInstaller..."
rm -rf build "dist/$APP_NAME.app" "dist/$APP_NAME"
"$VPY" -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name "$APP_NAME" --icon assets/icon.icns \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --add-data "ui:ui" --add-data "assets:assets" \
  --add-binary "$VENDOR/ffmpeg:vendor" --add-binary "$VENDOR/ffprobe:vendor" \
  --add-binary "$VENDOR/deno:vendor" --add-data "$VENDOR/FFMPEG-LICENSE.txt:vendor" \
  app.py
APP="dist/$APP_NAME.app"

echo "[6/8] Info.plist e assinatura local (ad-hoc)..."
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :NSDownloadsFolderUsageDescription" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSDownloadsFolderUsageDescription string O Camaradas Downloader salva os vídeos em Downloads, na pasta Vídeos baixados." "$PLIST"
/usr/libexec/PlistBuddy -c "Delete :LSMinimumSystemVersion" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 11.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Delete :CFBundleDisplayName" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string $APP_NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Delete :NSHumanReadableCopyright" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string Feito entre camaradas. Sem anúncio, sem cobrança, sem patrão." "$PLIST"
# Sem a assinatura da Apple (paga), assinamos "ad-hoc": no Apple Silicon todo
# executável precisa de pelo menos essa assinatura para rodar.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "   assinatura ad-hoc ok"

echo "[7/8] Autoteste do .app (sem janela)..."
"$APP/Contents/MacOS/$APP_NAME" --selftest --out "dist/selftest-$ARCH.json" \
  ${SELFTEST_URL:+--download "$SELFTEST_URL"}

echo "[8/8] DMG e zip para os amigos..."
DMG="dist/CamaradasDownloader-Mac-$LABEL.dmg"
STAGE="$TMPD/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Aplicativos"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
ZIP="Camaradas-Downloader-Mac-$LABEL.zip"
rm -f "$ZIP"
cp "LEIA-ME, CAMARADA (Mac).txt" "$TMPD/"
( cd dist && zip -q -X "$ROOT/$ZIP" "$(basename "$DMG")" )
( cd "$TMPD" && zip -q -X "$ROOT/$ZIP" "LEIA-ME, CAMARADA (Mac).txt" )

echo
echo "Pronto! $ZIP gerado ($(du -h "$ZIP" | cut -f1))."
