"""Mette affiancate le varianti fotografate (parte alta, 1440 px) in un foglio solo: riferimenti/prove/confronto_varianti.jpg"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

P = Path(__file__).parent / "riferimenti" / "prove"
NOMI = [("1 · v2 (D32+D31+D29)", "v2"), ("2 · Illusionista", "illusionista"), ("3 · Lusso", "lusso"), ("4 · Biologo", "biologo")]
f = ImageFont.truetype("arialbd.ttf", 34)
W, H = 1440, 1300
S = Image.new("RGB", (W * 2, (H + 60) * 2), (20, 20, 20))
d = ImageDraw.Draw(S)
for k, (lab, n) in enumerate(NOMI):
    x, y = (k % 2) * W, (k // 2) * (H + 60)
    p = P / f"{n}_1440.png"
    if p.exists():
        S.paste(Image.open(p).convert("RGB").crop((0, 0, W, H)), (x, y + 60))
    d.text((x + 14, y + 10), lab + ("" if p.exists() else "  (in arrivo)"), fill=(255, 255, 255), font=f)
S.thumbnail((2400, 2400))
S.save(P / "confronto_varianti.jpg", quality=86)
print(P / "confronto_varianti.jpg")
