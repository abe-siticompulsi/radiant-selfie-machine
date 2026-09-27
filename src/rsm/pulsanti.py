"""I pulsanti del messaggio di validazione, e la loro codifica.

Telegram restituisce solo la stringa `callback_data`, al massimo 64 byte: dentro
c'è tutto ciò che serve per decidere senza ambiguità — giro, persona, versione
della foto, azione. La versione rende innocuo un tocco su una foto nel frattempo
sostituita.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from . import regole
from .config import Motivo
from .telegram import Pulsanti

DOMANDA_MOTIVO = "Scrivi il motivo per"
ACCETTA = "ok"
ALTRO = "altro"
SENZA_MOTIVO = "no"
_PREFISSO = "v"


@dataclass(frozen=True)
class Tocco:
    giro_id: int
    soprannome: str
    versione: int
    azione: str


def dati_tocco(giro_id: int, soprannome: str, versione: int, azione: str) -> str:
    dati = f"{_PREFISSO}|{int(giro_id)}|{soprannome}|{int(versione)}|{azione}"
    if len(dati.encode("utf-8")) > 64:
        raise ValueError("callback_data oltre i 64 byte ammessi da Telegram")
    return dati


def leggi_tocco(dati: str) -> Tocco | None:
    parti = dati.split("|")
    if len(parti) != 5 or parti[0] != _PREFISSO:
        return None
    try:
        giro_id, versione = int(parti[1]), int(parti[3])
        soprannome = regole.soprannome_valido(parti[2])
    except (ValueError, regole.RegolaViolata):
        return None
    return Tocco(giro_id, soprannome, versione, parti[4])


def tastiera(giro_id: int, soprannome: str, versione: int, motivi: Sequence[Motivo]) -> Pulsanti:
    def pulsante(testo: str, azione: str) -> tuple[str, str]:
        return (testo, dati_tocco(giro_id, soprannome, versione, azione))

    righe: Pulsanti = [[pulsante("✅ Va bene", ACCETTA)]]
    per_motivo = [pulsante(m.etichetta, f"m{i}") for i, m in enumerate(motivi)]
    righe += [per_motivo[i : i + 2] for i in range(0, len(per_motivo), 2)]
    righe.append(
        [pulsante("✏️ Altro motivo…", ALTRO), pulsante("🔄 Un'altra, senza motivo", SENZA_MOTIVO)]
    )
    return righe


def motivo_del_pulsante(azione: str, motivi: Sequence[Motivo]) -> str | None:
    """Il testo per il giocatore del motivo predefinito scelto, o None."""
    if not azione.startswith("m"):
        return None
    try:
        indice = int(azione[1:])
    except ValueError:
        return None
    if not 0 <= indice < len(motivi):
        return None
    return motivi[indice].testo
