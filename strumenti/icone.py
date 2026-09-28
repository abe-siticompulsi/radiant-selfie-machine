"""Disegna le due icone della pagina. Si lancia una volta, e le icone si
committano:  uv run python strumenti/icone.py"""

from pathlib import Path

from PIL import Image, ImageDraw

CARTELLA = Path(__file__).resolve().parents[1] / "web" / "static"
FONDO = (43, 26, 74)
ORO = (242, 200, 90)
VIOLA = (160, 120, 255)


def icona(lato: int) -> Image.Image:
    immagine = Image.new("RGB", (lato, lato), FONDO)
    disegno = ImageDraw.Draw(immagine)
    margine = lato // 8
    disegno.rounded_rectangle(
        [margine, lato * 3 // 10, lato - margine, lato * 3 // 4], radius=lato // 12, fill=ORO
    )
    disegno.rectangle([lato * 3 // 8, lato // 5, lato * 5 // 8, lato * 3 // 10], fill=ORO)
    cx, cy = lato // 2, lato * 55 // 100
    for raggio, colore in ((lato * 16 // 100, FONDO), (lato // 10, VIOLA)):
        disegno.ellipse([cx - raggio, cy - raggio, cx + raggio, cy + raggio], fill=colore)
    return immagine


if __name__ == "__main__":
    for lato in (192, 512):
        icona(lato).save(CARTELLA / f"icona-{lato}.png")
