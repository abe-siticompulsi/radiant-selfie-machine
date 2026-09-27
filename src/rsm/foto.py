"""Le foto ricevute: controllo, impronta, file su disco.

Il controllo è severo di proposito: la foto arriva dalla rete e finirà in
`Miniatura/` passando per `ctc`. Solo JPEG, al massimo 8 MB, e solo se Pillow
riesce davvero a decodificarla: l'intestazione giusta non basta.

Il file definitivo porta la versione della foto, che decide il database. Per
questo si scrive prima un temporaneo, e lo si promuove quando la versione è
nota: una foto rifiutata dal database non lascia mai un file definitivo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from . import regole

MASSIMO = 8 * 1024 * 1024
PIXEL_MASSIMI = 50_000_000
_INIZIO_JPEG = b"\xff\xd8\xff"


class FotoRifiutata(ValueError):
    codice = 400


class FotoTroppoGrande(FotoRifiutata):
    codice = 413


class FotoNonJpeg(FotoRifiutata):
    codice = 415


def valida(dati: bytes) -> None:
    if len(dati) > MASSIMO:
        raise FotoTroppoGrande(f"la foto pesa {len(dati)} byte: al massimo {MASSIMO}")
    if not dati.startswith(_INIZIO_JPEG):
        raise FotoNonJpeg("non è un JPEG")
    try:
        with Image.open(BytesIO(dati)) as immagine:
            if immagine.format != "JPEG":
                raise FotoNonJpeg("non è un JPEG")
            larghezza, altezza = immagine.size
            if larghezza * altezza > PIXEL_MASSIMI:
                raise FotoTroppoGrande(f"la foto ha {larghezza}×{altezza} pixel: troppi")
            immagine.load()
    except FotoRifiutata:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as e:
        raise FotoNonJpeg("JPEG non decodificabile") from e


def impronta(dati: bytes) -> str:
    return hashlib.sha256(dati).hexdigest()


def _cartella_giro(cartella: Path, giro_id: int) -> Path:
    return cartella / str(int(giro_id))


def percorso(cartella: Path, giro_id: int, soprannome: str, versione: int) -> Path:
    regole.soprannome_valido(soprannome)
    return _cartella_giro(cartella, giro_id) / f"{soprannome}-{int(versione)}.jpg"


def salva_temporaneo(cartella: Path, giro_id: int, soprannome: str, dati: bytes) -> Path:
    regole.soprannome_valido(soprannome)
    destinazione = _cartella_giro(cartella, giro_id)
    destinazione.mkdir(parents=True, exist_ok=True)
    temporaneo = destinazione / f".{soprannome}-{uuid.uuid4().hex}.tmp"
    temporaneo.write_bytes(dati)
    return temporaneo


def promuovi(
    temporaneo: Path, cartella: Path, giro_id: int, soprannome: str, versione: int
) -> Path:
    finale = percorso(cartella, giro_id, soprannome, versione)
    os.replace(temporaneo, finale)
    return finale


def leggi(cartella: Path, giro_id: int, soprannome: str, versione: int) -> bytes:
    return percorso(cartella, giro_id, soprannome, versione).read_bytes()


def cancella(cartella: Path, giro_id: int, soprannome: str, versione: int) -> None:
    percorso(cartella, giro_id, soprannome, versione).unlink(missing_ok=True)


def cancella_giro(cartella: Path, giro_id: int) -> None:
    destinazione = _cartella_giro(cartella, giro_id)
    if destinazione.is_dir():
        shutil.rmtree(destinazione)
