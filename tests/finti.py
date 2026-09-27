"""I finti dei sistemi esterni.

Ognuno mette per iscritto una convinzione sul vero: dove quella convinzione
viene messa alla prova lo dice docs/differenze-fra-test-e-realta.md. Prima di
aggiungere un comportamento qui, la domanda è: quale convinzione sto scrivendo,
e dove la verifica il piano reale?
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from rsm.config import Impostazioni
from rsm.telegram import TelegramError


class TelegramFinto:
    """Risponde sempre subito e con successo, finché `guasto` non è impostato."""

    def __init__(self) -> None:
        self.chiamate: list[tuple[str, dict]] = []
        self.guasto: Exception | None = None
        self.aggiornamenti_da_dare: list[dict] = []
        self._ultimo_id = 100

    def _registra(self, nome: str, **argomenti) -> int:
        if self.guasto is not None:
            raise self.guasto
        self.chiamate.append((nome, argomenti))
        self._ultimo_id += 1
        return self._ultimo_id

    def scrivi(self, chat_id, testo):
        return self._registra("scrivi", chat_id=chat_id, testo=testo)

    def manda_foto(self, chat_id, dati, didascalia, pulsanti):
        return self._registra(
            "manda_foto", chat_id=chat_id, dati=dati, didascalia=didascalia, pulsanti=pulsanti
        )

    def modifica_didascalia(self, chat_id, messaggio, testo, pulsanti=None):
        self._registra(
            "modifica_didascalia", chat_id=chat_id, messaggio=messaggio, testo=testo, pulsanti=pulsanti
        )

    def chiedi_risposta(self, chat_id, testo):
        return self._registra("chiedi_risposta", chat_id=chat_id, testo=testo)

    def rispondi_tocco(self, tocco_id, testo):
        self._registra("rispondi_tocco", tocco_id=tocco_id, testo=testo)

    def aggiornamenti(self, offset, attesa):
        self._registra("aggiornamenti", offset=offset, attesa=attesa)
        dati, self.aggiornamenti_da_dare = self.aggiornamenti_da_dare, []
        return dati

    def webhook_attivo(self):
        return False

    def di_tipo(self, nome: str) -> list[dict]:
        return [argomenti for n, argomenti in self.chiamate if n == nome]


def telegram_guasto() -> TelegramError:
    return TelegramError("sendMessage: errore di rete (ConnectError)")


class NotificheFinte:
    """Ogni push è accettato. Nel vero accettato non vuol dire consegnato."""

    def __init__(self) -> None:
        self.inviate: list[dict] = []

    def a_persona(self, soprannome, titolo, testo, *, ttl):
        self.inviate.append({"soprannome": soprannome, "titolo": titolo, "testo": testo, "ttl": ttl})
        return 1


class Orologio:
    def __init__(self, inizio: datetime) -> None:
        self.adesso = inizio

    def __call__(self) -> datetime:
        return self.adesso

    def avanza(self, **quanto) -> None:
        self.adesso += timedelta(**quanto)


def impostazioni_di_prova(cartella: Path, **cambi) -> Impostazioni:
    base = Impostazioni(
        db=cartella / "rsm.sqlite",
        cartella_foto=cartella / "foto",
        token_bot="finto",
        gruppo_prova=-100,
        gruppo_party=None,
        admin_telegram_id=123456789,
        vapid_pem=cartella / "vapid.pem",
        vapid_contatto="mailto:prova@example.org",
    )
    return replace(base, **cambi)
