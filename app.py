# -*- coding: utf-8 -*-
"""Camaradas Downloader: janela pywebview + ponte com o motor.

Windows: WebView2. macOS: WKWebView (o WebKit do sistema). A interface é a mesma."""

import json
import os
import subprocess
import threading
import time

import webview

import engine
import messages

WIDTH = 356
SPLASH_MIN_SECONDS = 0.8

# JS extra injetado depois do carregamento. Não muda nada visual:
# avisa o Python quando a janela ganha foco e bloqueia o zoom do navegador embutido.
INJECT_JS = r"""
(function(){
  if (window.__camaradas) return; window.__camaradas = true;
  // A janela tem a altura exata do conteúdo: sem isso o navegador embutido deixa barras de
  // rolagem "grudadas" quando a janela cresce.
  document.documentElement.style.overflow = 'hidden';
  document.body.style.overflow = 'hidden';
  // A lista de formatos de áudio é absoluta e o #win corta o que passa da borda:
  // na tela de repouso M4A e OPUS ficariam fora. Enquanto a lista está aberta,
  // o quadro cresce o suficiente para ela (10px de folga, como o padding).
  var dd2 = document.getElementById('dd2'), win = document.getElementById('win');
  new MutationObserver(function(){
    win.style.minHeight = '';
    if (dd2.style.display === 'block') {
      var need = Math.ceil(dd2.getBoundingClientRect().bottom - win.getBoundingClientRect().top) + 10 + 4;
      if (need > win.offsetHeight) win.style.minHeight = need + 'px';
    }
    fit();
  }).observe(dd2, {attributes: true, attributeFilter: ['style']});
  window.addEventListener('focus', function(){ try{ window.pywebview.api.on_focus(); }catch(e){} });
  window.addEventListener('wheel', function(e){ if(e.ctrlKey || e.metaKey) e.preventDefault(); }, {passive:false});
  document.addEventListener('keydown', function(e){
    if ((e.ctrlKey || e.metaKey) && ['+','-','=','0'].indexOf(e.key) >= 0) e.preventDefault();
  });
})();
"""


# ------------------------------------------------------------- plataforma

def read_clipboard_text():
    """Texto da área de transferência: API do Windows ou pbpaste no Mac."""
    if engine.IS_WIN:
        return _read_clipboard_windows()
    if engine.IS_MAC:
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, timeout=2,
                               env=dict(os.environ, LANG="en_US.UTF-8"))
            return r.stdout.decode("utf-8", "replace")
        except Exception:
            return None
    return None


def _read_clipboard_windows():
    import ctypes
    from ctypes import wintypes
    CF_UNICODETEXT = 13
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def play(name):
    """Toca um som de assets/ sem travar a interface."""
    path = os.path.join(engine.resource_dir(), "assets", name)
    try:
        if engine.IS_WIN:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        elif engine.IS_MAC:
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


def reveal_file(path):
    """Abre o gerenciador de arquivos com o arquivo selecionado."""
    if engine.IS_WIN:
        subprocess.Popen('explorer /select,"%s"' % os.path.normpath(path))
    elif engine.IS_MAC:
        subprocess.Popen(["open", "-R", path])


def open_dir(path):
    if engine.IS_WIN:
        os.startfile(path)
    elif engine.IS_MAC:
        subprocess.Popen(["open", path])


def square_corners(window):
    """Windows 11 arredonda os cantos e pinta uma borda de 1px em toda janela.
    Desliga os dois para o quadro preto de 4px da interface ficar exato.
    (No Mac os cantos arredondados são do sistema e ficam como estão.)"""
    if not engine.IS_WIN:
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = window.native.Handle.ToInt64()
        dwm = ctypes.windll.dwmapi
        val = ctypes.c_int(1)  # DWMWCP_DONOTROUND
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(val), 4)
        color = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 34, ctypes.byref(color), 4)
    except Exception:
        pass  # Windows 10 não tem esses atributos (e nem arredonda)


# ------------------------------------------------------------------- API

class Api:
    """Métodos chamados pela interface via pywebview.api.*

    Atributos com "_" na frente não são expostos ao JavaScript.
    """

    def __init__(self):
        self._window = None
        self._last_file = None
        self._ready = False
        self._dl = engine.Downloader(self._on_progress, self._on_done)

    # ---- ponte Python -> JS
    def _js(self, fn, *args):
        w = self._window
        if not w:
            return
        code = "%s(%s)" % (fn, ",".join(json.dumps(a) for a in args))
        try:
            w.evaluate_js(code)
        except Exception:
            pass

    def _js_raw(self, code):
        try:
            if self._window:
                self._window.evaluate_js(code)
        except Exception:
            pass

    def _on_progress(self, pct, text):
        if text:
            self._js("setProgress", pct, text)
        else:
            self._js("setProgress", pct)

    def _on_done(self, ok, text, detail, kind, path):
        if kind == "cancelled":
            # Volta ao repouso: esconde o progresso e libera o botão
            self._js_raw("busy=false;$('prog').style.display='none';$('msg').style.display='none';fit();")
            return
        if ok:
            self._last_file = path
            play("success.wav")
            self._js("showMsg", True, text)
        else:
            play("error.wav")
            self._js("showMsg", False, text, detail or "")
            if kind == "private":
                self._add_hint(messages.LOGIN_HINT)

    def _add_hint(self, hint):
        # Dica logo abaixo da frase, dentro da mesma caixa de erro
        self._js_raw(
            "(function(){var m=$('msg'),p=m.querySelector('p'),h=document.createElement('p');"
            "h.className='px t';h.style.marginTop='6px';h.textContent=%s;p.after(h);fit();})()"
            % json.dumps(hint))

    def _paste_clipboard(self):
        try:
            text = (read_clipboard_text() or "").strip()
        except Exception:
            return
        if text.lower().startswith(("http://", "https://")) and engine.is_valid_url(text):
            self._js_raw("if(!$('url').value){setUrl(%s);}" % json.dumps(text))

    # ---- API exposta ao JS
    def start(self, url, mode, fmt, br):
        url = (url or "").strip()
        if not engine.is_valid_url(url):
            play("error.wav")
            self._js("showMsg", False, messages.INVALID_URL, "URL recebida: %r" % url)
            return False
        self._js("setProgress", 0, messages.PROGRESS_DOWNLOAD)
        return self._dl.start(url, mode, fmt, br)

    def cancel(self):
        self._dl.cancel()

    def open_folder(self):
        path = self._last_file
        try:
            if path and os.path.exists(path):
                reveal_file(path)
            else:
                open_dir(engine.output_dir())
        except Exception:
            pass

    def minimize(self):
        if self._window:
            self._window.minimize()

    def close(self):
        self._dl.cancel()
        if self._window:
            self._window.destroy()

    def fit(self, h):
        try:
            h = int(round(float(h)))
        except (TypeError, ValueError):
            return
        if self._window and h > 0:
            self._window.resize(WIDTH, h)

    def save_settings(self, obj):
        if not self._ready:  # ignora o save() que a página faz antes de restaurarmos
            return
        try:
            engine.save_settings(obj)
        except Exception:
            pass

    def on_focus(self):
        self._paste_clipboard()


def _fit_now(api):
    """Ajusta a altura direto pelo Python (não depende da ponte JS estar pronta)."""
    try:
        api.fit(api._window.evaluate_js("document.getElementById('win').offsetHeight"))
    except Exception:
        pass


def on_loaded(api):
    w = api._window
    # Espera a ponte pywebview.api ficar pronta (fit, save_settings...)
    for _ in range(50):
        try:
            if w.evaluate_js("!!(window.pywebview&&window.pywebview.api&&window.pywebview.api.fit)"):
                break
        except Exception:
            pass
        time.sleep(0.1)
    w.evaluate_js(INJECT_JS)
    t0 = time.time()
    api._js("setSplash", messages.SPLASH)
    _fit_now(api)
    w.show()
    square_corners(w)
    api._js("applySettings", engine.load_settings())
    api._ready = True
    try:
        engine.ensure_ytdlp()
    except Exception:
        pass  # sem internet etc.: segue com o que tem
    rest = SPLASH_MIN_SECONDS - (time.time() - t0)
    if rest > 0:
        time.sleep(rest)
    api._js("hideSplash")
    _fit_now(api)
    api._paste_clipboard()


def selftest(argv):
    """Autoteste sem janela, para o build (principalmente o do Mac, feito na nuvem):
      <app> --selftest [--download URL] [--out relatorio.json]
    Confere arquivos empacotados, ffmpeg, ffprobe, deno, certificados e o yt-dlp.
    Com --download, baixa a URL em vídeo e em MP3 de verdade."""
    import sys
    rep, ok = {"plataforma": sys.platform, "resource_dir": engine.resource_dir()}, True

    def run(args):
        r = engine._run_hidden(args, timeout=120)
        return r.returncode == 0, r.stdout.decode("utf-8", "replace").splitlines()[:1]

    for rel in ("ui/index.html", "ui/assets/PixelifySans.ttf", "assets/success.wav", "assets/error.wav"):
        exists = os.path.isfile(os.path.join(engine.resource_dir(), rel))
        rep["arquivo " + rel] = exists
        ok &= exists
    for name, args in (("ffmpeg", [engine.ffmpeg_path(), "-version"]),
                       ("ffprobe", [engine.ffprobe_path(), "-version"]),
                       ("deno", [engine.deno_path() or "deno-ausente", "--version"])):
        try:
            good, first = run(args)
        except Exception as e:
            good, first = False, [repr(e)]
        rep[name] = first
        ok &= good
    rep["github (certificados)"] = engine.fetch_latest_tag()
    ok &= rep["github (certificados)"] is not None
    engine.ensure_ytdlp()
    rep["yt-dlp"] = engine.local_version()
    ok &= rep["yt-dlp"] is not None

    if "--download" in argv:
        url = argv[argv.index("--download") + 1]
        for mode in ("video", "audio"):
            done = threading.Event()
            res = {}

            def fin(good, text, detail, kind, path, res=res, done=done):
                res.update(kind=kind, path=path, detail=(detail or "")[-300:])
                done.set()
            d = engine.Downloader(lambda p, t: None, fin)
            d.start(url, mode, "MP3", "none")
            done.wait(600)
            if res.get("path"):
                res["codecs"] = engine.probe(res["path"])[:2]
            rep["download " + mode] = res
            ok &= res.get("kind") == "ok"

    rep["resultado"] = "OK" if ok else "FALHOU"
    text = json.dumps(rep, ensure_ascii=False, indent=2)
    print(text)
    if "--out" in argv:
        with open(argv[argv.index("--out") + 1], "w", encoding="utf-8") as f:
            f.write(text)
    return 0 if ok else 1


def main():
    import sys
    if "--selftest" in sys.argv:
        sys.exit(selftest(sys.argv))
    api = Api()
    window = webview.create_window(
        "Camaradas Downloader",
        os.path.join(engine.resource_dir(), "ui", "index.html"),
        js_api=api,
        width=WIDTH,
        height=520,
        resizable=False,
        frameless=True,
        easy_drag=False,
        background_color="#0a1230",
        hidden=True,
    )
    api._window = window
    loaded_once = threading.Event()

    def _loaded():
        if loaded_once.is_set():
            return
        loaded_once.set()
        threading.Thread(target=on_loaded, args=(api,), daemon=True).start()

    window.events.loaded += _loaded
    window.events.closing += lambda: api._dl.cancel()
    webview.start()


if __name__ == "__main__":
    main()
