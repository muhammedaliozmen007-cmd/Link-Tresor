"""Erzeugt app/icon.ico und app/logo-*.png (blaues Schloss).

Kleine Größen werden pixelgenau ohne Weichzeichnung gezeichnet, damit das
Icon in Taskleiste und Titelleiste scharf bleibt. Benötigt Pillow.

    python tools/make_icon.py
"""

import os

from PIL import Image, ImageDraw

BLUE = (37, 99, 235, 255)
WHITE = (255, 255, 255, 255)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")


def draw(size, scale=1):
    """Zeichnet das Icon in size x size (intern mit Faktor scale)."""
    S = size * scale
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(v):  # Bruchteil der Kantenlänge -> ganze Pixel der Zielgröße, dann skaliert
        return round(v * size) * scale

    radius = max(px(0.2), 2 * scale)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=radius, fill=BLUE)

    # Bügel
    stroke = max(round(size * 0.1), 2) * scale
    sx0, sx1 = px(0.31), px(0.69)
    sy0, sy1 = px(0.16), px(0.56)
    d.rounded_rectangle((sx0, sy0, sx1 - scale, sy1), radius=(sx1 - sx0) // 2, fill=WHITE)
    d.rounded_rectangle(
        (sx0 + stroke, sy0 + stroke, sx1 - scale - stroke, sy1), radius=max((sx1 - sx0) // 2 - stroke, 0), fill=BLUE
    )

    # Körper
    bx0, bx1 = px(0.2), px(0.8)
    by0, by1 = px(0.44), px(0.86)
    d.rounded_rectangle((bx0, by0, bx1 - scale, by1 - scale), radius=max(px(0.08), scale), fill=WHITE)

    # Schlüsselloch
    kw = max(round(size * 0.12), 2) * scale
    cx = S // 2
    ky0 = px(0.56)
    d.ellipse((cx - kw // 2 - scale // 2, ky0, cx + kw // 2 + scale // 2 - 1, ky0 + kw), fill=BLUE)
    sw = max(kw // 2, scale)
    d.rectangle((cx - sw // 2, ky0 + kw // 2, cx + sw // 2 + (sw % 2) - 1, px(0.76)), fill=BLUE)

    if scale > 1:
        im = im.resize((size, size), Image.LANCZOS)
    return im


# 16 und 24 px: von Hand gezeichnet (B = blau, W = weiß, . = transparent)
GRID_16 = """
.BBBBBBBBBBBBBB.
BBBBBBBBBBBBBBBB
BBBBBBBBBBBBBBBB
BBBBBWWWWWWBBBBB
BBBBWWBBBBWWBBBB
BBBBWWBBBBWWBBBB
BBBBWWBBBBWWBBBB
BBBWWWWWWWWWWBBB
BBBWWWWWWWWWWBBB
BBBWWWWBBWWWWBBB
BBBWWWWBBWWWWBBB
BBBWWWWBBWWWWBBB
BBBWWWWWWWWWWBBB
BBBWWWWWWWWWWBBB
BBBBBBBBBBBBBBBB
.BBBBBBBBBBBBBB.
"""


GRID_24 = """
..BBBBBBBBBBBBBBBBBBBB..
.BBBBBBBBBBBBBBBBBBBBBB.
BBBBBBBBBBBBBBBBBBBBBBBB
BBBBBBBBBBBBBBBBBBBBBBBB
BBBBBBBBWWWWWWWWBBBBBBBB
BBBBBBBWWBBBBBBWWBBBBBBB
BBBBBBBWWBBBBBBWWBBBBBBB
BBBBBBBWWBBBBBBWWBBBBBBB
BBBBBBBWWBBBBBBWWBBBBBBB
BBBBBBBWWBBBBBBWWBBBBBBB
BBBBBBBWWBBBBBBWWBBBBBBB
BBBBWWWWWWWWWWWWWWWWBBBB
BBBBWWWWWWWWWWWWWWWWBBBB
BBBBWWWWWWBBBBWWWWWWBBBB
BBBBWWWWWWBBBBWWWWWWBBBB
BBBBWWWWWWWBBWWWWWWWBBBB
BBBBWWWWWWWBBWWWWWWWBBBB
BBBBWWWWWWWBBWWWWWWWBBBB
BBBBWWWWWWWWWWWWWWWWBBBB
BBBBWWWWWWWWWWWWWWWWBBBB
BBBBWWWWWWWWWWWWWWWWBBBB
BBBBBBBBBBBBBBBBBBBBBBBB
.BBBBBBBBBBBBBBBBBBBBBB.
..BBBBBBBBBBBBBBBBBBBB..
"""


def from_grid(grid):
    rows = grid.strip().splitlines()
    im = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
    colors = {"B": BLUE, "W": WHITE}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                im.putpixel((x, y), colors[ch])
    return im


def draw_exact(size, shackle_outer, shackle_inner, body, hole, stem, radius):
    """Pixelgenaue Variante mit festen Koordinaten (für 32 px)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BLUE)
    w = shackle_outer[2] - shackle_outer[0]
    d.rounded_rectangle(shackle_outer, radius=w // 2, fill=WHITE)
    wi = shackle_inner[2] - shackle_inner[0]
    d.rounded_rectangle(shackle_inner, radius=wi // 2, fill=BLUE)
    d.rounded_rectangle(body, radius=2, fill=WHITE)
    d.rounded_rectangle(hole, radius=1, fill=BLUE)
    d.rectangle(stem, fill=BLUE)
    return im


def render(size):
    if size == 16:
        return from_grid(GRID_16)
    if size == 24:
        return from_grid(GRID_24)
    if size == 32:
        return draw_exact(32, (10, 5, 21, 20), (13, 8, 18, 20), (6, 14, 25, 27), (13, 17, 18, 20), (15, 20, 16, 23), 6)
    return draw(size, 4)


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    images = {s: render(s) for s in sizes}
    images[256].save(
        os.path.join(OUT, "icon.ico"),
        sizes=[(s, s) for s in sizes],
        append_images=[images[s] for s in sizes[:-1]],
    )
    for s in (32, 48, 64):
        images[s].save(os.path.join(OUT, f"logo-{s}.png"))
    print("Icon erzeugt:", sizes)


if __name__ == "__main__":
    main()
