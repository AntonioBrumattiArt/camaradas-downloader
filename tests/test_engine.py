# -*- coding: utf-8 -*-
import os
import struct
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import engine  # noqa: E402
import messages  # noqa: E402


# ------------------------------------------------------------ URL

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    "https://youtu.be/aqz-KE-bpKQ",
    "http://example.com/video",
    "https://www.instagram.com/reel/abc123/",
    "  https://vimeo.com/123  ",
])
def test_valid_urls(url):
    assert engine.is_valid_url(url)


@pytest.mark.parametrize("url", [
    "", "   ", None, "banana", "www.youtube.com/watch?v=x", "ftp://example.com/a",
    "javascript:alert(1)", "https://", "https://exa mple.com", "file:///C:/x.mp4",
    "https://semponto/abc",
])
def test_invalid_urls(url):
    assert not engine.is_valid_url(url)


# ------------------------------------------------------- versões

def test_parse_version():
    assert engine.parse_version("2026.08.19") == (2026, 8, 19)
    assert engine.parse_version("2025.10.22.232846") == (2025, 10, 22, 232846)
    assert engine.parse_version("") is None
    assert engine.parse_version(None) is None


@pytest.mark.parametrize("remote,local,expected", [
    ("2026.09.01", "2026.08.19", True),
    ("2026.08.19", "2026.08.19", False),
    ("2026.08.01", "2026.08.19", False),
    ("2026.08.19.1", "2026.08.19", True),
    ("2026.10.2", "2026.9.30", True),
    ("2026.08.19", None, True),
    (None, "2026.08.19", False),
])
def test_is_newer(remote, local, expected):
    assert engine.is_newer(remote, local) is expected


# ------------------------------------------------------ progresso

def test_parse_progress_bytes():
    assert engine.parse_progress("CDPROG 512 1024 NA  50.0%") == 50.0


def test_parse_progress_estimate():
    assert engine.parse_progress("CDPROG 250 NA 1000  25.0%") == 25.0


def test_parse_progress_percent_fallback():
    assert engine.parse_progress("CDPROG NA NA NA  62.3%") == pytest.approx(62.3)


def test_parse_progress_clamped():
    assert engine.parse_progress("CDPROG 2000 1000 NA 200%") == 100.0


@pytest.mark.parametrize("line", [
    "", "[download] Destination: x.mp4", "CDFILE C:\\x.mp4", "CDPROG NA NA NA NA", None,
])
def test_parse_progress_ignores(line):
    assert engine.parse_progress(line) is None


# ------------------------------------------------------ argumentos

def _args(mode="video", fmt="MP3", br="none"):
    return engine.build_args("https://youtu.be/x", mode, fmt, br, "C:\\out", "C:\\ff", None)


def _val(args, flag):
    return args[args.index(flag) + 1]


def test_video_args():
    a = _args()
    assert _val(a, "-f") == "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*+ba/b"
    assert _val(a, "--merge-output-format") == "mp4"
    assert "-x" not in a
    assert _val(a, "-o") == "%(title).150B [%(id)s].%(ext)s"
    assert "--windows-filenames" in a and "--newline" in a and "--no-playlist" in a
    assert _val(a, "--ffmpeg-location") == "C:\\ff"
    assert _val(a, "-P") == "C:\\out"
    assert a[-2:] == ["--", "https://youtu.be/x"]
    assert "--cookies-from-browser" not in a


@pytest.mark.parametrize("fmt,codec,quality", [
    ("MP3", "mp3", True), ("WAV", "wav", False), ("FLAC", "flac", False),
    ("M4A", "m4a", True), ("OPUS", "opus", False),
])
def test_audio_args(fmt, codec, quality):
    a = _args("audio", fmt)
    assert "-x" in a
    assert _val(a, "--audio-format") == codec
    assert ("--audio-quality" in a) is quality
    if quality:
        assert _val(a, "--audio-quality") == "0"
    assert "--merge-output-format" not in a
    assert engine.expected_extension("audio", fmt) == "." + codec


@pytest.mark.parametrize("br", ["firefox", "edge", "chrome"])
def test_browser_args(br):
    a = _args(br=br)
    assert _val(a, "--cookies-from-browser") == br


def test_browser_none_or_garbage():
    assert "--cookies-from-browser" not in _args(br="none")
    assert "--cookies-from-browser" not in _args(br="opera; rm -rf")


def test_deno_arg():
    a = engine.build_args("https://youtu.be/x", "video", "MP3", "none", "o", "f", "C:\\d\\deno.exe")
    assert _val(a, "--js-runtimes") == "deno:C:\\d\\deno.exe"


# ---------------------------------------------------- classificação

CASES = [
    ("ERROR: [youtube] xyz: Private video. Sign in if you've been granted access to this video",
     "none", "private"),
    ("ERROR: [Instagram] abc: Requested content is not available, rate-limit reached or login "
     "required. Use --cookies, --cookies-from-browser, --username and --password", "none", "private"),
    ("ERROR: [youtube] xyz: Sign in to confirm your age. This video may be inappropriate for some users.",
     "none", "private"),
    ("ERROR: [youtube] xyz: Sign in to confirm you're not a bot. Use --cookies-from-browser", "none", "rate"),
    ("ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests", "none", "rate"),
    ("ERROR: [youtube] xyz: Video unavailable. This video has been removed by the uploader",
     "none", "removed"),
    ("ERROR: [youtube] xyz: Video unavailable", "none", "removed"),
    ("ERROR: Unsupported URL: https://example.com/", "none", "unsupported"),
    ("ERROR: [youtube] xyz: The uploader has not made this video available in your country",
     "none", "geo"),
    ("ERROR: [Niconico] sm9: This video is not available in your country due to geo restriction",
     "none", "geo"),
    ("ERROR: [generic] Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>",
     "none", "network"),
    ("ERROR: [youtube] x: Unable to download API page: [WinError 10060] Uma tentativa de conexão falhou",
     "none", "network"),
    ("ERROR: [youtube] x: Failed to resolve 'www.youtube.com' ([Errno 11001] getaddrinfo failed)",
     "none", "network"),
    # mensagens típicas do macOS
    ("ERROR: [youtube] x: Unable to download API page: <urlopen error [Errno 8] nodename nor "
     "servname provided, or not known>", "none", "network"),
    ("ERROR: [youtube] x: Unable to download webpage: [Errno 61] Connection refused", "none", "network"),
    ("ERROR: unable to open for writing: [Errno 1] Operation not permitted: '/Users/x/Downloads/a.part'",
     "none", "disk"),
    ("ERROR: Failed to decrypt cookies: could not find chrome key in keychain", "chrome", "cookies"),
    ("ERROR: [Netflix] x: This video is DRM protected", "none", "drm"),
    ("ERROR: The requested site is known to use DRM protection. It will NOT be supported.",
     "none", "drm"),
    ("ERROR: unable to write data: [Errno 28] No space left on device", "none", "disk"),
    ("ERROR: unable to open for writing: [Errno 13] Permission denied: 'C:\\x.part'", "none", "disk"),
    ("ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271",
     "chrome", "cookies"),
    ("ERROR: Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927",
     "chrome", "cookies"),
    ("ERROR: could not find firefox cookies database in C:\\Users\\x\\AppData", "firefox", "cookies"),
    ("ERROR: 'banana' is not a valid URL. Set --default-search", "none", "invalid"),
    ("ERROR: [youtube] xyz: Requested format is not available. Use --list-formats", "none", "generic"),
    ("ERROR: [youtube] xyz: Unable to extract initial player response; please report this issue",
     "none", "generic"),
    ("ERROR: fragment 3 not found, unable to continue", "none", "generic"),
    ("ERROR: Postprocessing: Conversion failed!", "none", "generic"),
    ("ERROR: something completely weird happened", "none", "unknown"),
    ("", "none", "unknown"),
]


@pytest.mark.parametrize("stderr,browser,kind", CASES)
def test_classify(stderr, browser, kind):
    got_kind, phrase, _ = engine.classify_error(stderr, browser)
    assert got_kind == kind


def test_classify_uses_error_lines_not_warnings():
    err = ("WARNING: [youtube] Some formats are not available in your country\n"
           "ERROR: [youtube] xyz: Private video. Sign in if you've been granted access")
    assert engine.classify_error(err)[0] == "private"


def test_login_failure_without_browser_is_not_cookie_error():
    err = "ERROR: Could not copy Chrome cookie database."
    assert engine.classify_error(err, "none")[0] != "cookies"


def test_phrases_and_retry():
    assert engine.classify_error("ERROR: Video unavailable") == ("removed", messages.REMOVED, False)
    assert engine.classify_error("ERROR: Postprocessing: x")[2] is True
    assert engine.classify_error("ERROR: weird")[1] == messages.UNKNOWN


def test_cookie_messages():
    assert messages.cookies_message("chrome") == \
        "O Chrome guarda a carteirinha a sete chaves. Tente o Firefox ou o Edge."
    assert messages.cookies_message("edge") == \
        "O Edge guarda a carteirinha a sete chaves. Tente o Firefox ou o Chrome."
    assert messages.cookies_message("firefox") == \
        "O Firefox guarda a carteirinha a sete chaves. Tente o Edge ou o Chrome."


# ------------------------------------------------------ recodificação

def test_recode_args_copy_when_ok():
    a = engine.recode_args("in.webm", "out.mp4", "h264", "opus")
    assert a[a.index("-c:v") + 1] == "copy"
    assert a[a.index("-c:a") + 1] == "aac"


def test_recode_args_full():
    a = engine.recode_args("in.webm", "out.mp4", "vp9", "opus")
    assert a[a.index("-c:v") + 1] == "libx264"
    assert "yuv420p" in a


# ------------------------------------------------------ configurações

def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "app_data_dir", lambda: str(tmp_path))
    assert engine.load_settings() == engine.DEFAULT_SETTINGS
    engine.save_settings({"mode": "audio", "fmt": "FLAC", "br": "firefox"})
    assert engine.load_settings() == {"mode": "audio", "fmt": "FLAC", "br": "firefox"}
    engine.save_settings({"mode": "xx", "fmt": "AVI", "br": "opera"})
    assert engine.load_settings() == {"mode": "audio", "fmt": "FLAC", "br": "firefox"}


# ------------------------------------------------------ plataforma

def test_tag_from_release_url():
    assert engine.tag_from_release_url(
        "https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19") == "2026.08.19"
    assert engine.tag_from_release_url("https://github.com/yt-dlp/yt-dlp/releases") is None
    assert engine.tag_from_release_url(None) is None


def test_latest_tag_falls_back_when_api_refuses(monkeypatch):
    class Resp:
        def __init__(self, url):
            self.url = url
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def geturl(self):
            return "https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.01"

    def fake_get(url, timeout):
        if "api.github.com" in url:
            raise OSError("HTTP Error 403: rate limit exceeded")
        return Resp(url)
    monkeypatch.setattr(engine, "_http_get", fake_get)
    assert engine.fetch_latest_tag() == "2026.10.01"


def test_ytdlp_asset_names():
    assert engine.ytdlp_asset_name("win32") == "yt-dlp.exe"
    assert engine.ytdlp_asset_name("darwin") == "yt-dlp_macos"


def test_paths_follow_platform():
    assert engine.ytdlp_path().endswith(engine.ytdlp_asset_name())
    assert engine.ffmpeg_path().endswith("ffmpeg.exe" if engine.IS_WIN else "ffmpeg")
    if engine.IS_MAC:
        assert "Library/Application Support/CamaradasDownloader" in engine.app_data_dir()
        assert engine.downloads_dir() == os.path.join(os.path.expanduser("~"), "Downloads")


def test_mac_app_data_dir(monkeypatch):
    monkeypatch.setattr(engine, "IS_WIN", False)
    monkeypatch.setattr(engine, "IS_MAC", True)
    assert engine.app_data_dir().replace("\\", "/").endswith(
        "Library/Application Support/CamaradasDownloader")
    assert engine.exe_name("ffmpeg") == "ffmpeg"
    assert engine.popen_kwargs() == {"start_new_session": True}


def test_windows_popen_has_no_window(monkeypatch):
    monkeypatch.setattr(engine, "IS_WIN", True)
    assert engine.popen_kwargs() == {"creationflags": engine.CREATE_NO_WINDOW}
    assert engine.exe_name("ffmpeg") == "ffmpeg.exe"


def test_ssl_context_has_certificates():
    ctx = engine.ssl_context()
    assert ctx.verify_mode.name == "CERT_REQUIRED"
    assert ctx.cert_store_stats()["x509_ca"] > 0


def test_icns_is_valid():
    with open(os.path.join(ROOT, "assets", "icon.icns"), "rb") as f:
        data = f.read()
    assert data[:4] == b"icns"
    assert struct.unpack(">I", data[4:8])[0] == len(data)
    i, tags = 8, []
    while i < len(data):
        tag, n = data[i:i + 4], struct.unpack(">I", data[i + 4:i + 8])[0]
        assert data[i + 8:i + 16] == b"\x89PNG\r\n\x1a\n"
        tags.append(tag)
        i += n
    assert i == len(data)
    assert b"ic10" in tags and b"icp4" in tags


# ------------------------------------------------ nova tentativa única

def _fake_downloader(monkeypatch, tmp_path, errors):
    monkeypatch.setattr(engine, "output_dir", lambda: str(tmp_path))
    monkeypatch.setattr(engine, "ytdlp_path", lambda: __file__)
    monkeypatch.setattr(engine, "local_version", lambda path=None: "2026.08.19")
    calls, updates, result = [], [], {}
    d = engine.Downloader(lambda p, t: None, lambda *a: result.setdefault("done", a),
                          on_retry_update=lambda: updates.append(1))

    def fake(url, mode, fmt, br, out):
        calls.append(1)
        return False, None, errors[min(len(calls) - 1, len(errors) - 1)]
    monkeypatch.setattr(d, "_download", fake)
    d.busy = True
    d._run("https://youtu.be/x", "video", "MP3", "none")
    return calls, updates, result["done"]


def test_retry_once_on_generic(monkeypatch, tmp_path):
    calls, updates, done = _fake_downloader(monkeypatch, tmp_path, ["ERROR: Unable to extract x"])
    assert len(calls) == 2 and len(updates) == 1
    assert done[0] is False and done[1] == messages.GENERIC


def test_no_retry_on_user_errors(monkeypatch, tmp_path):
    calls, updates, done = _fake_downloader(monkeypatch, tmp_path, ["ERROR: Private video"])
    assert len(calls) == 1 and not updates
    assert done[1] == messages.PRIVATE and done[3] == "private"
