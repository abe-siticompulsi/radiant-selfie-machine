"""Immagini vere, generate al volo: un finto di JPEG non proverebbe niente."""

from io import BytesIO

from PIL import Image


def jpeg(larghezza: int = 64, altezza: int = 48, colore=(120, 80, 200)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (larghezza, altezza), colore).save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (0, 0, 0)).save(buffer, "PNG")
    return buffer.getvalue()
