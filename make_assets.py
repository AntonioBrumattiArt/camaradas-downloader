# -*- coding: utf-8 -*-
"""Gera os assets do app: sons chiptune (.wav), ícone do Windows (.ico) e do Mac (.icns).

Uso: python make_assets.py
"""

import os
import shutil
import struct
import wave
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
RATE = 44100

# Foice e martelo 16x16, o mesmo desenho do <symbol id="hs"> da interface
HS_RECTS = [(4, 1, 3), (3, 2, 5), (9, 2, 2), (3, 3, 2), (9, 3, 3), (3, 4, 2), (10, 4, 3),
            (4, 5, 2), (10, 5, 4), (4, 6, 3), (9, 6, 2), (12, 6, 3), (6, 7, 4), (13, 7, 1),
            (7, 8, 2), (6, 9, 4), (5, 10, 2), (9, 10, 2), (4, 11, 2), (10, 11, 2), (3, 12, 2),
            (11, 12, 2), (2, 13, 2), (12, 13, 2)]
RED = (0xC8, 0x10, 0x2E, 255)
YELLOW = (0xF2, 0xB7, 0x05, 255)
BLACK = (0, 0, 0, 255)


# ------------------------------------------------------------------ sons

def note_freq(name):
    """'C5' -> Hz (A4 = 440)."""
    names = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    semis = names[name[0]]
    rest = name[1:]
    if rest.startswith("#"):
        semis += 1
        rest = rest[1:]
    octave = int(rest)
    return 440.0 * 2 ** ((semis + (octave - 4) * 12) / 12.0)


def square(freq, dur, vol=0.22, duty=0.5):
    n = int(RATE * dur)
    out = []
    if freq <= 0:
        return [0.0] * n
    attack, release = int(RATE * 0.004), int(RATE * 0.03)
    for i in range(n):
        phase = (i * freq / RATE) % 1.0
        s = vol if phase < duty else -vol
        env = 1.0
        if i < attack:
            env = i / attack
        elif i > n - release:
            env = max(0.0, (n - i) / release)
        out.append(s * env)
    return out


def melody(notes, duty=0.5, vol=0.22):
    samples = []
    for name, dur in notes:
        f = 0 if name == "-" else note_freq(name)
        samples += square(f, dur, vol, duty)
    return samples


def mix(a, b):
    n = max(len(a), len(b))
    a = a + [0.0] * (n - len(a))
    b = b + [0.0] * (n - len(b))
    return [max(-1.0, min(1.0, x + y)) for x, y in zip(a, b)]


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))


def make_sounds():
    # Fanfarra da vitória: arpejo subindo + acorde final (~1,5 s)
    lead = melody([("G4", 0.09), ("C5", 0.09), ("E5", 0.09), ("G5", 0.18), ("-", 0.04),
                   ("E5", 0.09), ("G5", 0.36), ("-", 0.03), ("C6", 0.55)], duty=0.5, vol=0.2)
    bass = melody([("C3", 0.27), ("G3", 0.31), ("C3", 0.09), ("E3", 0.39), ("C3", 0.58)],
                  duty=0.25, vol=0.14)
    write_wav(os.path.join(ASSETS, "success.wav"), mix(lead, bass))
    # Erro: dois "bonks" descendo (~0,4 s)
    err = melody([("D#3", 0.12), ("-", 0.04), ("A2", 0.24)], duty=0.25, vol=0.25)
    write_wav(os.path.join(ASSETS, "error.wav"), err)


# ----------------------------------------------------------------- ícone

def png_bytes(width, height, pixels):
    """PNG RGBA mínimo (sem dependências)."""
    raw = b"".join(b"\x00" + b"".join(bytes(pixels[y * width + x]) for x in range(width))
                   for y in range(height))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def icon_grid():
    """Grade 20x20: borda preta de 1, fundo vermelho, foice e martelo amarelos no meio."""
    size = 20
    grid = [[RED] * size for _ in range(size)]
    for i in range(size):
        grid[0][i] = grid[size - 1][i] = grid[i][0] = grid[i][size - 1] = BLACK
    for x, y, w in HS_RECTS:
        for dx in range(w):
            grid[y + 2][x + 2 + dx] = YELLOW
    return grid


def render_icon(px):
    grid = icon_grid()
    n = len(grid)
    pixels = []
    for y in range(px):
        gy = y * n // px
        for x in range(px):
            pixels.append(grid[gy][x * n // px])
    return png_bytes(px, px, pixels)


def make_ico(cache):
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    images = [cache(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for s, img in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
        data += img
    with open(os.path.join(ASSETS, "icon.ico"), "wb") as f:
        f.write(header + entries + data)
    with open(os.path.join(ASSETS, "icon.png"), "wb") as f:
        f.write(cache(256))


# Tipos do .icns com PNG dentro (macOS 10.7+), com o tamanho real de cada um
ICNS_TYPES = [(b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"icp6", 64), (b"ic12", 64),
              (b"ic07", 128), (b"ic13", 256), (b"ic08", 256), (b"ic14", 512), (b"ic09", 512),
              (b"ic10", 1024)]


def icns_bytes(cache):
    """Monta um .icns (ícone do Mac) só com PNGs, sem precisar do iconutil."""
    body = b""
    for tag, size in ICNS_TYPES:
        img = cache(size)
        body += tag + struct.pack(">I", len(img) + 8) + img
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def make_icns(cache):
    with open(os.path.join(ASSETS, "icon.icns"), "wb") as f:
        f.write(icns_bytes(cache))


def main():
    os.makedirs(ASSETS, exist_ok=True)
    make_sounds()
    rendered = {}

    def cache(size):
        if size not in rendered:
            rendered[size] = render_icon(size)
        return rendered[size]
    make_ico(cache)
    make_icns(cache)
    # A interface carrega a fonte por caminho relativo (ui/assets/PixelifySans.ttf)
    font = os.path.join(ASSETS, "PixelifySans.ttf")
    if os.path.isfile(font):
        os.makedirs(os.path.join(ROOT, "ui", "assets"), exist_ok=True)
        shutil.copyfile(font, os.path.join(ROOT, "ui", "assets", "PixelifySans.ttf"))
    print("Assets gerados em", ASSETS)


if __name__ == "__main__":
    main()
