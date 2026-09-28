"""La configurazione del servizio, dall'ambiente.

Sul server la contiene tutta `config/rsm.env` (permessi 600); nel repository
c'è solo `config.esempio/rsm.env`. Un valore mancante o malformato ferma
l'avvio con un messaggio che nomina la variabile: mai un default silenzioso per
un segreto o per un gruppo Telegram.

La sicura: finché `RSM_GRUPPO` è vuoto, l'annuncio va nel gruppo di prova. Si
arma scrivendo l'identificativo del party in quel file, dopo la prova generale:
così resta traccia in un file che si rilegge.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .regole import MOTIVO_MASSIMO


class ConfigurazioneErrata(ValueError):
    """Una variabile d'ambiente manca o non ha la forma attesa."""


@dataclass(frozen=True)
class Motivo:
    etichetta: str  # sul pulsante: corta, o Telegram la taglia sul telefono
    testo: str  # per il giocatore: può essere più lungo


MOTIVI_PREDEFINITI = (
    Motivo("Sfocata", "sfocata"),
    Motivo("Troppo buia", "troppo buia"),
    Motivo("Viso non inquadrato", "viso non inquadrato"),
    Motivo("Tagliata", "tagliata (controlla che tutta la testa sia ben visibile nella foto)"),
)


@dataclass(frozen=True)
class Impostazioni:
    db: Path
    cartella_foto: Path
    token_bot: str
    gruppo_prova: int
    gruppo_party: int | None
    admin_telegram_id: int
    vapid_pem: Path
    vapid_contatto: str
    rinvio_minuti: int = 10
    motivi: tuple[Motivo, ...] = MOTIVI_PREDEFINITI

    @property
    def sicura_inserita(self) -> bool:
        return self.gruppo_party is None

    @property
    def gruppo_annuncio(self) -> int:
        return self.gruppo_prova if self.gruppo_party is None else self.gruppo_party


def _testo(env: Mapping[str, str], nome: str) -> str:
    valore = (env.get(nome) or "").strip()
    if not valore:
        raise ConfigurazioneErrata(f"{nome} manca")
    return valore


def _intero(env: Mapping[str, str], nome: str, predefinito: int | None = None) -> int:
    grezzo = (env.get(nome) or "").strip()
    if not grezzo:
        if predefinito is None:
            raise ConfigurazioneErrata(f"{nome} manca")
        return predefinito
    try:
        return int(grezzo)
    except ValueError:
        raise ConfigurazioneErrata(f"{nome} non è un numero intero: {grezzo!r}") from None


def _motivi(env: Mapping[str, str]) -> tuple[Motivo, ...]:
    grezzo = (env.get("RSM_MOTIVI") or "").strip()
    if not grezzo:
        return MOTIVI_PREDEFINITI
    try:
        lista = json.loads(grezzo)
    except json.JSONDecodeError:
        raise ConfigurazioneErrata("RSM_MOTIVI non è JSON valido") from None
    if not isinstance(lista, list) or not 1 <= len(lista) <= 8:
        raise ConfigurazioneErrata("RSM_MOTIVI deve essere una lista di 1-8 motivi")
    motivi = []
    for voce in lista:
        if not (
            isinstance(voce, dict)
            and isinstance(voce.get("etichetta"), str)
            and isinstance(voce.get("testo"), str)
        ):
            raise ConfigurazioneErrata("RSM_MOTIVI: ogni motivo ha «etichetta» e «testo»")
        etichetta, testo = voce["etichetta"].strip(), voce["testo"].strip()
        if not 0 < len(etichetta) <= 30 or not 0 < len(testo) <= MOTIVO_MASSIMO:
            raise ConfigurazioneErrata(
                f"RSM_MOTIVI: etichetta fino a 30 caratteri, testo fino a {MOTIVO_MASSIMO}"
            )
        motivi.append(Motivo(etichetta, testo))
    return tuple(motivi)


def _contatto(env: Mapping[str, str]) -> str:
    """Il «sub» di VAPID: il servizio push di Apple rifiuta un contatto vuoto."""
    contatto = _testo(env, "RSM_VAPID_CONTATTO")
    if contatto.startswith("mailto:"):
        valido = re.fullmatch(r"[^@\s]+@[^@\s]+", contatto.removeprefix("mailto:")) is not None
    elif contatto.startswith("https://"):
        valido = len(contatto) > len("https://")
    else:
        valido = False
    if not valido:
        raise ConfigurazioneErrata(
            "RSM_VAPID_CONTATTO deve essere mailto:<indirizzo con @> o https://<sito>"
        )
    return contatto


def da_ambiente(env: Mapping[str, str]) -> Impostazioni:
    rinvio = _intero(env, "RSM_RINVIO_MINUTI", 10)
    if rinvio < 1:
        raise ConfigurazioneErrata("RSM_RINVIO_MINUTI deve essere almeno 1")
    party = (env.get("RSM_GRUPPO") or "").strip()
    return Impostazioni(
        db=Path(_testo(env, "RSM_DB")),
        cartella_foto=Path(_testo(env, "RSM_FOTO")),
        token_bot=_testo(env, "RSM_BOT_TOKEN"),
        gruppo_prova=_intero(env, "RSM_GRUPPO_PROVA"),
        gruppo_party=_intero(env, "RSM_GRUPPO") if party else None,
        admin_telegram_id=_intero(env, "RSM_ADMIN_TELEGRAM_ID"),
        vapid_pem=Path(_testo(env, "RSM_VAPID_PEM")),
        vapid_contatto=_contatto(env),
        rinvio_minuti=rinvio,
        motivi=_motivi(env),
    )


def percorso_db(env: Mapping[str, str]) -> Path:
    return Path(_testo(env, "RSM_DB"))


def url_base(env: Mapping[str, str]) -> str:
    base = _testo(env, "RSM_URL_BASE").rstrip("/")
    locale = base.startswith(("http://127.0.0.1", "http://localhost"))
    if not (base.startswith("https://") or locale):
        raise ConfigurazioneErrata("RSM_URL_BASE deve essere un indirizzo https")
    return base
