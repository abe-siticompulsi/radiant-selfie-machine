"""Le regole del giro e delle foto. Niente I/O: solo date, stati e ruoli.

Tutto ciò che dipende dall'ora la riceve come argomento, così i test provano
le 48 ore, le 12 ore e i 30 giorni senza aspettare. Le date hanno sempre il
fuso orario: il servizio lavora in UTC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

DURATA_GIRO = timedelta(hours=48)
SOGLIA_RIAPERTURA = timedelta(hours=12)
CONSERVAZIONE = timedelta(days=30)
MOTIVO_MASSIMO = 200

IN_ATTESA = "in_attesa"
ACCETTATA = "accettata"
DA_RIFARE = "da_rifare"

GIOCATORE = "giocatore"
MASTER = "master"
ADMIN = "admin"
CTC = "ctc"
RUOLI = (GIOCATORE, MASTER, ADMIN, CTC)
CHI_SCATTA = frozenset({GIOCATORE, MASTER, ADMIN})
CHI_APRE = frozenset({MASTER, ADMIN})

_SOPRANNOME = re.compile(r"^[a-z0-9_-]{1,32}$")


class RegolaViolata(Exception):
    """Un'operazione che le regole non ammettono in questo stato."""


@dataclass(frozen=True)
class Giro:
    id: int
    aperto_alle: datetime
    aperto_da: str
    chiuso_alle: datetime | None = None
    sessione: str | None = None


def fine(giro: Giro) -> datetime:
    """Il momento in cui il giro smette di essere aperto."""
    scadenza = giro.aperto_alle + DURATA_GIRO
    if giro.chiuso_alle is not None and giro.chiuso_alle < scadenza:
        return giro.chiuso_alle
    return scadenza


def aperto(giro: Giro, ora: datetime) -> bool:
    return ora < fine(giro)


@dataclass(frozen=True)
class Apertura:
    """Cosa fare quando qualcuno preme «Apri il giro».

    `riusa`: il giro già aperto da restituire così com'è.
    `chiudi`: il giro vecchio da chiudere prima di aprirne uno nuovo.
    Entrambi `None`: si apre un giro nuovo e basta.
    """

    riusa: Giro | None
    chiudi: Giro | None


def decidi_apertura(ultimo: Giro | None, ora: datetime) -> Apertura:
    """Due serate non stanno mai a meno di 12 ore l'una dall'altra: un giro
    aperto da meno di 12 ore è quello di stasera, uno più vecchio no."""
    if ultimo is None or not aperto(ultimo, ora):
        return Apertura(riusa=None, chiudi=None)
    if ora - ultimo.aperto_alle < SOGLIA_RIAPERTURA:
        return Apertura(riusa=ultimo, chiudi=None)
    return Apertura(riusa=None, chiudi=ultimo)


def stato_dopo_invio(attuale: str | None, ruolo: str) -> str:
    """Lo stato di una foto appena ricevuta.

    La foto di Alberto (admin) è accettata all'arrivo: il suo «Invia» è già la
    conferma di chi valida. Una foto accettata è definitiva.
    """
    if ruolo not in CHI_SCATTA:
        raise RegolaViolata(f"il ruolo {ruolo} non scatta")
    if attuale == ACCETTATA:
        raise RegolaViolata("la foto è già stata accettata: è definitiva")
    return ACCETTATA if ruolo == ADMIN else IN_ATTESA


def motivo_valido(testo: str) -> str:
    pulito = testo.strip()
    if not pulito:
        raise RegolaViolata("il motivo è vuoto")
    if len(pulito) > MOTIVO_MASSIMO:
        raise RegolaViolata(
            f"il motivo è lungo {len(pulito)} caratteri: al massimo {MOTIVO_MASSIMO}"
        )
    return pulito


def verifica_esito(esito: str, motivo: str | None) -> str | None:
    """Controlla una decisione su una foto e restituisce il motivo ripulito.

    Che la foto sia davvero in attesa lo controlla chi chiama, perché è un
    conflitto con lo stato (409), non una richiesta sbagliata (400).
    """
    if esito not in (ACCETTATA, DA_RIFARE):
        raise RegolaViolata(f"esito sconosciuto: {esito!r}")
    if motivo is None:
        return None
    if esito != DA_RIFARE:
        raise RegolaViolata("il motivo accompagna solo la richiesta di un'altra foto")
    return motivo_valido(motivo)


def rinvio_fino_a(ora: datetime, minuti: int) -> datetime:
    return ora + timedelta(minutes=minuti)


def rinvio_da_notificare(
    fino_a: datetime, notificato: bool, stato_foto: str | None, ora: datetime
) -> bool:
    """Un rinvio scaduto si notifica una volta sola, e solo a chi non ha già
    una foto in attesa o accettata."""
    return not notificato and fino_a <= ora and stato_foto not in (IN_ATTESA, ACCETTATA)


def da_cancellare(giro: Giro, ora: datetime) -> bool:
    return ora >= fine(giro) + CONSERVAZIONE


def soprannome_valido(soprannome: str) -> str:
    """Lo stesso alfabeto di `validate.nickname` in close-the-circle: il
    soprannome finisce in un nome di file, qui e là."""
    if not isinstance(soprannome, str) or not _SOPRANNOME.fullmatch(soprannome):
        raise RegolaViolata(f"soprannome non valido: {soprannome!r}")
    return soprannome


def stato_pannello(stato_foto: str | None, rinvio_attivo: bool) -> str:
    """Quello che il pannello di master e admin mostra per una persona."""
    if stato_foto is not None:
        return stato_foto
    return "rinviato" if rinvio_attivo else "nessuna"
