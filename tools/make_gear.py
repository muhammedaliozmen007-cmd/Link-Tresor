"""Erzeugt das Zahnrad-Symbol für den Einstellungen-Button (PC + Android). Benötigt Pillow.

    python tools/make_gear.py
"""

import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COLOR = (230, 230, 230, 255)  # wie die Schrift im Dark Mode
TEETH = 8


def draw(size, color=COLOR):
    S = size * 8  # groß zeichnen, dann glatt verkleinern
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S / 2
    r_out, r_in, r_hole = S * 0.47, S * 0.36, S * 0.15
    # Zähne als Polygon: abwechselnd außen (Zahn) und innen (Lücke)
    pts = []
    for i in range(TEETH * 4):
        a = 2 * math.pi * i / (TEETH * 4) - math.pi / 2
        r = r_out if i % 4 in (1, 2) else r_in
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=color)
    d.ellipse((c - r_in, c - r_in, c + r_in, c + r_in), fill=color)
    d.ellipse((c - r_hole, c - r_hole, c + r_hole, c + r_hole), fill=(0, 0, 0, 0))
    return im.resize((size, size), Image.LANCZOS)


def main():
    for size in (16, 20, 24, 32):
        draw(size).save(os.path.join(ROOT, "app", f"gear-{size}.png"))
    white = (255, 255, 255, 255)
    for density, size in {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}.items():
        folder = os.path.join(ROOT, "android", "app", "src", "main", "res", f"drawable-{density}")
        os.makedirs(folder, exist_ok=True)
        draw(size, white).save(os.path.join(folder, "ic_settings.png"))
    print("Zahnräder erzeugt.")


if __name__ == "__main__":
    main()
