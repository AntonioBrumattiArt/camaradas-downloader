# Camaradas Downloader (Windows e macOS)

Interface de desktop para baixar um vídeo ou áudio por vez a partir de um link, usando yt-dlp e ffmpeg. Feito em Python + pywebview. No Windows a janela usa o WebView2; no Mac, o WKWebView (o WebKit do sistema). A interface é a mesma nos dois: `ui/index.html`.

## Estrutura

| Arquivo | Função |
|---|---|
| `app.py` | Janela sem moldura, `js_api` (start, cancel, open_folder, minimize, close, fit, save_settings), splash, colagem automática, sons, autoteste (`--selftest`) |
| `engine.py` | yt-dlp: checagem/atualização, argumentos, execução, progresso, cancelamento, classificação de erros; ffmpeg: conferência H.264/AAC e recodificação. As diferenças entre Windows e Mac ficam na seção "plataforma" |
| `messages.py` | Todas as frases que o usuário lê |
| `ui/index.html` | Interface (cópia byte a byte de `ui/tela_referencia.html`) |
| `assets/` | Fonte, sons (`success.wav`, `error.wav`), ícones (`icon.ico` Windows, `icon.icns` Mac) |
| `vendor/` | Windows: `ffmpeg.exe`, `ffprobe.exe`, `deno.exe` (não versionados) |
| `vendor_mac/<arch>/` | Mac: baixados pelo `build_mac.sh` (não versionados) |
| `make_assets.py` | Gera sons e ícones |
| `tests/` | Testes pytest |
| `build.bat` + `installer.iss` | Build do Windows (PyInstaller + Inno Setup) |
| `build_mac.sh` | Build do Mac (PyInstaller + .app + .dmg) |
| `.github/workflows/build-mac.yml` | Build do Mac na nuvem do GitHub, sem precisar de um Mac |

## O que muda entre Windows e Mac

| | Windows | Mac |
|---|---|---|
| Dados do app (yt-dlp, settings.json) | `%LOCALAPPDATA%\CamaradasDownloader` | `~/Library/Application Support/CamaradasDownloader` |
| yt-dlp | `yt-dlp.exe` | `yt-dlp_macos` (universal) |
| Downloads | pasta Downloads real (API do Windows) | `~/Downloads` |
| Processos | `CREATE_NO_WINDOW`; cancelar com `taskkill /T` | grupo de processos próprio; cancelar com `killpg` |
| Sons | `winsound` | `afplay` |
| Área de transferência | API do Windows | `pbpaste` |
| Abrir pasta | `explorer /select,` | `open -R` |
| Cantos da janela | retos (DWM) | arredondados (padrão do macOS) |
| Certificados HTTPS | do sistema | `certifi` (o Python empacotado no Mac não acha os do sistema) |

## Como gerar

### Windows
1. Python 3.12+ e Inno Setup 6 (`winget install JRSoftware.InnoSetup`).
2. Em `vendor/`: `ffmpeg.exe` e `ffprobe.exe` (build estático GPL de https://github.com/yt-dlp/FFmpeg-Builds) e `deno.exe` (https://github.com/denoland/deno/releases).
3. `build.bat` gera `Camaradas-Downloader.zip` (instalador + `LEIA-ME, CAMARADA.txt`).

### Mac, sem ter um Mac (GitHub Actions)
1. Suba esta pasta para um repositório no GitHub (os binários grandes ficam de fora pelo `.gitignore`).
2. Aba **Actions** > **Build Mac** > **Run workflow**.
3. Em uns 15 minutos, baixe em **Artifacts** os dois zips: `Camaradas-Downloader-Mac-AppleSilicon` e `Camaradas-Downloader-Mac-Intel`. Cada um traz o `.dmg` e o `LEIA-ME, CAMARADA (Mac).txt`, além do relatório do autoteste (`selftest-*.json`).

### Mac, num Mac
`bash build_mac.sh` (macOS 11+, Python 3.10+). Gera para a arquitetura daquele Mac. O script baixa ffmpeg/ffprobe (https://ffmpeg.martin-riedl.de, builds estáticos para macOS) e deno (GitHub, conferindo o SHA-256), monta o `.app`, assina ad-hoc, roda o autoteste e gera `.dmg` + zip.

Testes: `python -m pytest -q tests`. Autoteste do app empacotado: `<app> --selftest [--download URL] [--out relatorio.json]`.

## Atualização do yt-dlp

Ao abrir, o app consulta `api.github.com/repos/yt-dlp/yt-dlp/releases/latest`, compara com `--version` e, se houver versão nova (ou nenhuma), baixa o binário do sistema para um temporário, confere o SHA-256 publicado (`SHA2-256SUMS`), testa o `--version` e só então troca o arquivo. Sem internet, segue com a versão local. Se um download falhar por erro genérico/desconhecido, atualiza e tenta de novo uma vez.

## Assinatura no Mac

O app não tem assinatura paga da Apple (Developer ID, US$ 99/ano) nem notarização. Ele é assinado "ad-hoc", o mínimo para rodar no Apple Silicon. Por isso o Gatekeeper avisa na primeira abertura; o `LEIA-ME, CAMARADA (Mac).txt` explica como liberar. Com uma conta de desenvolvedor Apple, dá para trocar o `codesign --sign -` do `build_mac.sh` pela identidade Developer ID e adicionar `xcrun notarytool`.

## Licenças

- **yt-dlp**: Unlicense (domínio público). Baixado na primeira execução direto do GitHub oficial.
- **FFmpeg**: Windows, build `gpl` do yt-dlp/FFmpeg-Builds; Mac, builds estáticos de ffmpeg.martin-riedl.de. Ambos sob **GPL v3** (incluem libx264 etc.). Texto em `vendor/FFMPEG-LICENSE.txt`. Código-fonte: https://github.com/FFmpeg/FFmpeg
- **Deno**: MIT. https://github.com/denoland/deno
- **Pixelify Sans**: SIL Open Font License 1.1 (`assets/OFL-PixelifySans.txt`).
- **pywebview**: BSD-3-Clause. **pythonnet** (Windows): MIT. **PyObjC** (Mac): MIT. **certifi**: MPL-2.0.

## Aviso

Baixar conteúdo de terceiros pode violar os termos de uso das plataformas e direitos autorais. Use só com conteúdo seu, de domínio público, com licença que permita (ex.: Creative Commons) ou com autorização. O app não contorna DRM, login nem contas privadas: só usa a sessão que o próprio usuário já tem no navegador dele.
