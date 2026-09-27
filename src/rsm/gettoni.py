"""I gettoni personali: il segreto che sta nel link di ciascuno.

Nel database finisce solo l'impronta: chi legge il database non può
ricostruire i link.
"""

from __future__ import annotations

import hashlib
import secrets


def genera() -> str:
    return secrets.token_urlsafe(32)


def impronta(gettone: str) -> str:
    return hashlib.sha256(gettone.encode("utf-8")).hexdigest()
