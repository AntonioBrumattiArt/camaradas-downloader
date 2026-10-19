# -*- coding: utf-8 -*-
"""Motor do Camaradas Downloader: yt-dlp (checagem/atualização, execução,
progresso, cancelamento), ffmpeg (conferência e recodificação) e configurações.

Roda no Windows e no macOS. O que muda entre os dois fica concentrado nas
funções da seção "plataforma"."""

import ctypes
import hashlib
import json
import os
import re
import signal
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlparse

import messages

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

CREATE_NO_WINDOW = 0x08000000

GITHUB_API_LATEST = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_RELEASE_BASE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
YTDLP_SUMS_URL = YTDLP_RELEASE_BASE + "SHA2-256SUMS"
USER_AGENT = "CamaradasDownloader/1.1"

OUTPUT_TEMPLATE = "%(title).150B [%(id)s].%(ext)s"
VIDEO_FORMAT = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*+ba/b"
AUDIO_FORMATS = {"MP3": "mp3", "WAV": "wav", "FLAC": "flac", "M4A": "m4a", "OPUS": "opus"}
BROWSERS = ("firefox", "edge", "chrome")

PROGRESS_PREFIX = "CDPROG"
FILE_PREFIX = "CDFILE"
PROGRESS_TEMPLATE = (
    "download:" + PROGRESS_PREFIX +
    " %(progress.downloaded_bytes)s %(progress.total_bytes)s"
    " %(progress.total_bytes_estimate)s %(progress._percent_str)s"
)

DEFAULT_SETTINGS = {"mode": "video", "fmt": "MP3", "br": "none"}


# ------------------------------------------------------------- plataforma

def exe_name(base):
    """'ffmpeg' -> 'ffmpeg.exe' no Windows, 'ffmpeg' no Mac."""
    return base + ".exe" if IS_WIN else base


def ytdlp_asset_name(platform=None):
    """Nome do binário oficial do yt-dlp no release do GitHub para cada sistema."""
    platform = platform or sys.platform
    if platform == "win32":
        return "yt-dlp.exe"
    if platform == "darwin":
        return "yt-dlp_macos"          # universal: Intel e Apple Silicon
    return "yt-dlp_linux"


def popen_kwargs():
    """Argumentos para subprocess: sem janela de console no Windows; no Mac,
    um grupo de processos próprio para o cancelar derrubar os filhos juntos."""
    if IS_WIN:
        return {"creationflags": CREATE_NO_WINDOW}
    return {"start_new_session": True}


def kill_tree(proc):
    """Encerra o processo e os filhos (ffmpeg, deno, processo interno do yt-dlp)."""
    if not proc or proc.poll() is not None:
        return
    try:
        if IS_WIN:
            _run_hidden(["taskkill", "/PID", str(proc.pid), "/T", "/F"], timeout=15)
        else:
            os.killpg(proc.pid, signal.SIGKILL)   # pgid == pid por causa do start_new_session
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def ssl_context():
    """Certificados para o urllib. No Mac o Python empacotado não acha os do
    sistema; o certifi (empacotado junto) resolve. No Windows usa o padrão."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# ---------------------------------------------------------------- caminhos

def resource_dir():
    """Pasta dos arquivos do app (ui, assets, vendor), no Python ou no PyInstaller."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def app_data_dir():
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif IS_MAC:
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "CamaradasDownloader")


def bin_dir():
    return os.path.join(app_data_dir(), "bin")


def ytdlp_path():
    return os.path.join(bin_dir(), ytdlp_asset_name())


def vendor_dir():
    return os.path.join(resource_dir(), "vendor")


def settings_path():
    return os.path.join(app_data_dir(), "settings.json")


def downloads_dir():
    """Pasta Downloads real do usuário. No Windows pergunta à API (a pasta pode
    ter sido movida); no Mac é sempre ~/Downloads."""
    if IS_WIN:
        try:
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
            # FOLDERID_Downloads {374DE290-123F-4565-9164-39C4925E467B}
            fid = GUID(0x374DE290, 0x123F, 0x4565,
                       (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            ptr = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(ptr)) == 0:
                path = ptr.value
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                if path:
                    return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


def output_dir():
    path = os.path.join(downloads_dir(), "Vídeos baixados")
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------- configurações

def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("mode") in ("video", "audio"):
            s["mode"] = data["mode"]
        if data.get("fmt") in AUDIO_FORMATS:
            s["fmt"] = data["fmt"]
        if data.get("br") in ("none",) + BROWSERS:
            s["br"] = data["br"]
    except Exception:
        pass
    return s


def save_settings(obj):
    s = dict(DEFAULT_SETTINGS)
    s.update(load_settings())
    if isinstance(obj, dict):
        if obj.get("mode") in ("video", "audio"):
            s["mode"] = obj["mode"]
        if obj.get("fmt") in AUDIO_FORMATS:
            s["fmt"] = obj["fmt"]
        if obj.get("br") in ("none",) + BROWSERS:
            s["br"] = obj["br"]
    os.makedirs(app_data_dir(), exist_ok=True)
    tmp = settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f)
    os.replace(tmp, settings_path())
    return s


# --------------------------------------------------------- funções puras

def is_valid_url(url):
    """Aceita só http(s) com host plausível e sem espaços."""
    if not isinstance(url, str):
        return False
    url = url.strip()
    if not url or any(c.isspace() for c in url):
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = p.hostname or ""
    return "." in host or host == "localhost"


def parse_version(text):
    """'2026.08.19' -> (2026, 8, 19). None se não houver números."""
    if not text:
        return None
    nums = re.findall(r"\d+", str(text))
    return tuple(int(n) for n in nums) if nums else None


def is_newer(remote, local):
    """True se a versão remota for mais nova que a local (ou se não há local)."""
    r, l = parse_version(remote), parse_version(local)
    if r is None:
        return False
    if l is None:
        return True
    return r > l


def parse_progress(line):
    """Lê a linha do --progress-template e devolve o percentual (0-100) ou None."""
    if not line:
        return None
    line = line.strip()
    if not line.startswith(PROGRESS_PREFIX):
        return None
    parts = line[len(PROGRESS_PREFIX):].split()
    if len(parts) >= 3:
        def num(v):
            try:
                return float(v)
            except ValueError:
                return None
        done, total, estimate = num(parts[0]), num(parts[1]), num(parts[2])
        total = total or estimate
        if done is not None and total:
            return max(0.0, min(100.0, done * 100.0 / total))
    m = re.search(r"(\d+(?:\.\d+)?)%", line)
    if m:
        return max(0.0, min(100.0, float(m.group(1))))
    return None


def build_args(url, mode, fmt, br, outdir, ffmpeg_dir, deno_path=None):
    """Monta a lista de argumentos do yt-dlp (sem o executável)."""
    args = [
        "--ignore-config",
        "--no-playlist",
        "--newline",
        "--progress",
        "--progress-template", PROGRESS_TEMPLATE,
        "--print", "after_move:" + FILE_PREFIX + " %(filepath)s",
        "--encoding", "utf-8",
        "--windows-filenames",
        "--no-mtime",
        "-P", outdir,
        "-o", OUTPUT_TEMPLATE,
        "--ffmpeg-location", ffmpeg_dir,
    ]
    if deno_path:
        args += ["--js-runtimes", "deno:" + deno_path]
    if mode == "audio":
        afmt = AUDIO_FORMATS.get(str(fmt).upper(), "mp3")
        args += ["-f", "ba/b", "-x", "--audio-format", afmt]
        if afmt in ("mp3", "m4a"):
            args += ["--audio-quality", "0"]
    else:
        args += ["-f", VIDEO_FORMAT, "--merge-output-format", "mp4"]
    if br in BROWSERS:
        args += ["--cookies-from-browser", br]
    args += ["--", url]
    return args


def expected_extension(mode, fmt):
    if mode == "audio":
        return "." + AUDIO_FORMATS.get(str(fmt).upper(), "mp3")
    return ".mp4"


# ------------------------------------------------------ classificação

_COOKIE_FAIL = re.compile(
    r"could not copy .*cookie|cookies? database|failed to decrypt|dpapi|app.bound"
    r"|could not find .*(cookie|profile|browser)|failed to (load|read|extract) cookies"
    r"|unsupported keyring|keyring|keychain|cookies?.*(locked|permission denied)")
_DRM = re.compile(r"\bdrm\b")
_INVALID = re.compile(r"is not a valid url")
_UNSUPPORTED = re.compile(r"unsupported url")
_BOT = re.compile(r"not a bot|confirm you.?re not a robot|captcha")
_PRIVATE = re.compile(
    r"private video|video is private|is private|this account is private|login required"
    r"|log ?in to|sign in to|requires? (authentication|login|account)|authentication required"
    r"|account authentication|members.only|join this channel|age.restricted|age restricted"
    r"|use --cookies|cookies for the authentication|logged.in|not logged in|empty media response")
_RATE = re.compile(r"http error 429|too many requests|rate.?limit|throttl")
_GEO = re.compile(
    r"not available in your (country|region)|geo.?restrict|in your country|your location"
    r"|from your (country|region)|blocked it in your|geoblock|not available in your area")
_NETWORK = re.compile(
    r"getaddrinfo|failed to resolve|name or service not known|nodename nor servname"
    r"|temporary failure in name resolution|network is unreachable|no route to host"
    r"|connection refused|failed to establish a new connection|unable to connect to proxy"
    r"|proxyerror|winerror 100(5[0-9]|6[0-9])|winerror 1100[1-4]|errno 1100[1-4]"
    r"|errno 8\]|errno 5[01]\]|errno 6[01]\]"
    r"|connection (reset|aborted)|timed out|timeout|ssl: |certificate verify failed"
    r"|no internet|offline")
_REMOVED = re.compile(
    r"video unavailable|has been removed|been taken down|no longer available|does not exist"
    r"|http error 404|404: not found|not found|terminated|content (isn.t|is not) available"
    r"|is unavailable|is not available|not available|deleted|removed by")
_DISK = re.compile(
    r"no space left|errno 28|winerror 112|disk (is )?full|not enough space"
    r"|permission denied|access is denied|acesso negado|winerror 5\b|errno 13"
    r"|operation not permitted|errno 1\]"
    r"|unable to open for writing|read-only file system")
# Falhas que costumam ser do yt-dlp/rede e não do vídeo (checadas antes de "removido")
_BROKEN = re.compile(r"requested format|fragment|postprocessing|unable to extract|giving up")
_GENERIC = re.compile(
    r"unable to download|http error|giving up|fragment|postprocessing|ffmpeg|unable to extract"
    r"|requested format|did not get any data|unable to rename|incomplete|content-length")

RETRYABLE = ("generic", "unknown")


def classify_error(stderr, browser="none"):
    """Classifica a saída de erro do yt-dlp.

    Devolve (tipo, frase, pode_tentar_de_novo). O tipo "private" pede a dica do login.
    """
    text = stderr or ""
    error_lines = [l for l in text.splitlines() if l.strip().upper().startswith("ERROR")]
    t = ("\n".join(error_lines) if error_lines else text).lower()

    if browser in BROWSERS and _COOKIE_FAIL.search(t):
        return "cookies", messages.cookies_message(browser), False
    if _DRM.search(t):
        return "drm", messages.DRM, False
    if _INVALID.search(t):
        return "invalid", messages.INVALID_URL, False
    if _UNSUPPORTED.search(t):
        return "unsupported", messages.UNSUPPORTED, False
    if _BOT.search(t):
        return "rate", messages.RATE_LIMIT, False
    if _PRIVATE.search(t):
        return "private", messages.PRIVATE, False
    if _RATE.search(t):
        return "rate", messages.RATE_LIMIT, False
    if _GEO.search(t):
        return "geo", messages.GEO_BLOCKED, False
    if _NETWORK.search(t):
        return "network", messages.NO_INTERNET, False
    if _DISK.search(t):
        return "disk", messages.DISK, False
    if _BROKEN.search(t):
        return "generic", messages.GENERIC, True
    if _REMOVED.search(t):
        return "removed", messages.REMOVED, False
    if _GENERIC.search(t):
        return "generic", messages.GENERIC, True
    return "unknown", messages.UNKNOWN, True


# ------------------------------------------------------- atualização

def _run_hidden(args, timeout=60):
    return subprocess.run(args, capture_output=True, timeout=timeout,
                          stdin=subprocess.DEVNULL, **popen_kwargs())


def local_version(path=None):
    path = path or ytdlp_path()
    if not os.path.isfile(path):
        return None
    try:
        r = _run_hidden([path, "--version"], timeout=60)
        if r.returncode == 0:
            v = r.stdout.decode("utf-8", "replace").strip()
            return v or None
    except Exception:
        pass
    return None


def _http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


def fetch_latest_tag(timeout=8):
    """Versão mais nova no GitHub ou None (sem internet, limite da API...)."""
    try:
        with _http_get(GITHUB_API_LATEST, timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("tag_name") or None
    except Exception:
        return None


def download_ytdlp(dest=None, timeout=30):
    """Baixa o yt-dlp novo para um temporário, confere o SHA-256 e o --version
    e só então troca o arquivo. Nunca deixa o app sem yt-dlp."""
    dest = dest or ytdlp_path()
    name = ytdlp_asset_name()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".download"
    try:
        expected = None
        try:
            with _http_get(YTDLP_SUMS_URL, timeout) as r:
                for line in r.read().decode("utf-8", "replace").splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].lstrip("*") == name:
                        expected = parts[0].lower()
        except Exception:
            expected = None
        h = hashlib.sha256()
        with _http_get(YTDLP_RELEASE_BASE + name, timeout) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                h.update(chunk)
                f.write(chunk)
        if expected and h.hexdigest() != expected:
            raise IOError("SHA-256 do yt-dlp não confere")
        if not IS_WIN:
            os.chmod(tmp, 0o755)   # no Mac o arquivo precisa ser executável
        if os.path.getsize(tmp) < 1_000_000 or not local_version(tmp):
            raise IOError("yt-dlp baixado não executa")
        for _ in range(10):
            try:
                os.replace(tmp, dest)
                return True
            except PermissionError:
                time.sleep(0.5)
        return False
    except Exception:
        return False
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def ensure_ytdlp():
    """Checa e atualiza o yt-dlp. Devolve True se existe um yt-dlp utilizável."""
    local = local_version()
    latest = fetch_latest_tag()
    if local is None:
        download_ytdlp()
        return local_version() is not None
    if latest and is_newer(latest, local):
        download_ytdlp()
    return True


# ----------------------------------------------------------- ffmpeg

def ffmpeg_path():
    return os.path.join(vendor_dir(), exe_name("ffmpeg"))


def ffprobe_path():
    return os.path.join(vendor_dir(), exe_name("ffprobe"))


def deno_path():
    p = os.path.join(vendor_dir(), exe_name("deno"))
    return p if os.path.isfile(p) else None


def probe(path):
    """Devolve (vcodec, acodec, duração_em_s) do arquivo."""
    r = _run_hidden([ffprobe_path(), "-v", "error", "-show_entries",
                     "stream=codec_type,codec_name:format=duration", "-of", "json", path],
                    timeout=60)
    data = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    v = a = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s.get("codec_name")
        elif s.get("codec_type") == "audio" and a is None:
            a = s.get("codec_name")
    try:
        dur = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        dur = 0.0
    return v, a, dur


def recode_args(src, dst, vcodec, acodec):
    """Argumentos do ffmpeg para deixar o MP4 em H.264 + AAC (copia o que já está certo)."""
    args = [ffmpeg_path(), "-y", "-hide_banner", "-nostats", "-progress", "pipe:1", "-i", src,
            "-map", "0:v:0?", "-map", "0:a:0?"]
    if vcodec == "h264":
        args += ["-c:v", "copy"]
    else:
        args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    if acodec in ("aac", None):
        args += ["-c:a", "copy"]
    else:
        args += ["-c:a", "aac", "-b:a", "320k"]
    args += ["-movflags", "+faststart", dst]
    return args


# --------------------------------------------------------- download

class Cancelled(Exception):
    pass


class Downloader:
    """Um download por vez. Os callbacks são chamados na thread do download.

    on_progress(pct, texto_ou_None); on_done(ok, frase, detalhe, kind, caminho)
    """

    def __init__(self, on_progress, on_done, on_retry_update=None):
        self.on_progress = on_progress
        self.on_done = on_done
        self.on_retry_update = on_retry_update or ensure_ytdlp
        self._lock = threading.Lock()
        self._proc = None
        self._cancel = threading.Event()
        self._thread = None
        self.busy = False

    def start(self, url, mode, fmt, br):
        with self._lock:
            if self.busy:
                return False
            self.busy = True
            self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(url, mode, fmt, br), daemon=True)
        self._thread.start()
        return True

    def cancel(self):
        self._cancel.set()
        kill_tree(self._proc)

    # ---- fluxo principal
    def _run(self, url, mode, fmt, br):
        try:
            self._run_inner(url, mode, fmt, br)
        except Cancelled:
            self.busy = False
            self.on_done(None, None, None, "cancelled", None)
        except Exception as e:  # nunca deixar o camarada sem resposta
            self.busy = False
            self.on_done(False, messages.UNKNOWN, repr(e), "unknown", None)

    def _run_inner(self, url, mode, fmt, br):
        try:
            out = output_dir()
        except OSError as e:
            self.busy = False
            self.on_done(False, messages.DISK, str(e), "disk", None)
            return
        if not os.path.isfile(ytdlp_path()) or local_version() is None:
            if not ensure_ytdlp():
                self.busy = False
                self.on_done(False, messages.NO_INTERNET,
                             "yt-dlp ausente e não foi possível baixá-lo.", "network", None)
                return
        for attempt in (0, 1):
            ok, path, err = self._download(url, mode, fmt, br, out)
            if self._cancel.is_set():
                raise Cancelled()
            if ok:
                if mode != "audio":
                    path = self._ensure_h264_aac(path)
                if not path or not os.path.isfile(path):
                    self.busy = False
                    self.on_done(False, messages.UNKNOWN, err or "Arquivo final não encontrado.",
                                 "unknown", None)
                    return
                self.busy = False
                self.on_done(True, messages.SUCCESS, None, "ok", path)
                return
            kind, phrase, retry = classify_error(err, br)
            if retry and attempt == 0:
                self.on_progress(0, None)
                try:
                    self.on_retry_update()
                except Exception:
                    pass
                if self._cancel.is_set():
                    raise Cancelled()
                continue
            self.busy = False
            self.on_done(False, phrase, err, kind, None)
            return

    def _download(self, url, mode, fmt, br, out):
        before = set(os.listdir(out))
        args = [ytdlp_path()] + build_args(url, mode, fmt, br, out, vendor_dir(), deno_path())
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        err_lines = []
        final = []
        try:
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                env=env, cwd=out, **popen_kwargs())
        except OSError as e:
            return False, None, "Não foi possível iniciar o yt-dlp: %r" % (e,)

        def read_err():
            for raw in self._proc.stderr:
                err_lines.append(raw.decode("utf-8", "replace").rstrip())
                del err_lines[:-300]
        t = threading.Thread(target=read_err, daemon=True)
        t.start()

        phase, last, shown = 0, 0.0, 0.0
        for raw in self._proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith(FILE_PREFIX + " "):
                final.append(line[len(FILE_PREFIX) + 1:].strip())
                continue
            pct = parse_progress(line)
            if pct is None:
                continue
            if pct < last - 30:  # recomeçou do zero: é o próximo arquivo (ex.: o áudio)
                phase += 1
            last = pct
            val = pct * 0.9 if phase == 0 else 90 + pct * 0.08
            if val > shown:
                shown = val
                self.on_progress(shown, None)
        code = self._proc.wait()
        t.join(timeout=5)
        err = "\n".join(err_lines)
        if self._cancel.is_set():
            self._cleanup(out, before)
            raise Cancelled()
        if code == 0:
            path = final[-1] if final else None
            if not path or not os.path.isfile(path):
                path = self._newest_new_file(out, before, expected_extension(mode, fmt))
            return True, path, err
        self._cleanup(out, before)
        return False, None, err or ("yt-dlp terminou com código %d" % code)

    def _ensure_h264_aac(self, path):
        """Confere o MP4; se não for H.264/AAC, recodifica com o ffmpeg."""
        try:
            vcodec, acodec, dur = probe(path)
        except Exception:
            return path
        if vcodec in ("h264", None) and acodec in ("aac", None) and path.lower().endswith(".mp4"):
            return path
        base = os.path.splitext(path)[0]
        dst = base + ".mp4"
        tmp = base + ".recode.mp4"
        self.on_progress(0, messages.PROGRESS_CONVERT)
        self._proc = subprocess.Popen(recode_args(path, tmp, vcodec, acodec),
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      stdin=subprocess.DEVNULL, **popen_kwargs())
        for raw in self._proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_us=") and dur > 0:
                try:
                    self.on_progress(min(99.0, int(line.split("=")[1]) / 1e6 / dur * 100), None)
                except ValueError:
                    pass
        code = self._proc.wait()
        if self._cancel.is_set():
            _remove_quiet(tmp)
            _remove_quiet(path)
            raise Cancelled()
        if code != 0:
            _remove_quiet(tmp)
            return path
        if os.path.abspath(path) != os.path.abspath(dst):
            _remove_quiet(path)
        os.replace(tmp, dst)
        return dst

    @staticmethod
    def _newest_new_file(out, before, ext):
        new = [os.path.join(out, n) for n in os.listdir(out) if n not in before]
        new = [p for p in new if p.lower().endswith(ext)] or new
        return max(new, key=os.path.getmtime) if new else None

    @staticmethod
    def _cleanup(out, before):
        """Apaga só o que este download criou (arquivos parciais)."""
        for _ in range(10):
            left = []
            for n in os.listdir(out):
                if n in before:
                    continue
                p = os.path.join(out, n)
                if os.path.isfile(p) and not _remove_quiet(p):
                    left.append(p)
            if not left:
                return
            time.sleep(0.5)


def _remove_quiet(path):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False
