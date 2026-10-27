"""Draw Turing's icon (the blue orb from the app) into turing/assets/turing.ico."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 512
OUT = Path(__file__).resolve().parent.parent / "turing" / "assets" / "turing.ico"


def orb() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # Radial gradient: light highlight top-left, cobalt body, deep blue rim.
    stops = [(0.0, (201, 212, 255)), (0.48, (45, 79, 208)), (1.0, (23, 42, 133))]
    cx, cy, r = SIZE * 0.36, SIZE * 0.32, SIZE * 0.62
    px = img.load()
    for y in range(SIZE):
        for x in range(SIZE):
            d = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / r)
            for (a, ca), (b, cb) in zip(stops, stops[1:]):
                if d <= b:
                    t = (d - a) / (b - a)
                    px[x, y] = tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3)) + (255,)
                    break
    mask = Image.new("L", (SIZE, SIZE), 0)
    pad = SIZE * 0.06
    ImageDraw.Draw(mask).ellipse((pad, pad, SIZE - pad, SIZE - pad), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.5))
    img.putalpha(mask)
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    orb().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Wrote {OUT}")
