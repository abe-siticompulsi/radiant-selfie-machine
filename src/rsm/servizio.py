"""Il cuore del servizio: le operazioni che la pagina, il bot e `ctc` chiedono.

Qui si incontrano le regole (pure), lo store, le foto su disco, Telegram e il
push. Le rotte HTTP e il bot restano sottili: chiamano questi metodi e ne
traducono le eccezioni. Ciò che parla con un sistema esterno lento e non serve
alla risposta (`invita`, `annuncia_foto`, `dopo_decisione`) sta in un metodo a
parte, che l'HTTP esegue dopo aver risposto.

Un guasto di Telegram o del push non fa mai fallire l'operazione: si registra,
e la risposta dice la verità su cosa è partito e cosa no.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from . import foto, gettoni, pulsanti, regole
from .config import Impostazioni
from .regole import Giro
from .store import Foto, Persona, Store
from .telegram import Pulsanti, TelegramError

log = logging.getLogger(__name__)

TITOLO = "📸 Selfie per la miniatura"
TESTO_INVITO_GRUPPO = "📸 È il momento del selfie per la miniatura!"
TESTO_INVITO_PUSH = "È il momento del selfie!"
TESTO_ACCETTATA = "La tua foto è stata accettata"
TESTO_ALTRA_FOTO = "Alberto chiede un'altra foto"
TTL_INVITO = 30 * 60
TTL_ESITO = 12 * 60 * 60


class ErroreServizio(Exception):
    codice = 400


class RichiestaErrata(ErroreServizio):
    codice = 400


class NonTrovato(ErroreServizio):
    codice = 404


class Conflitto(ErroreServizio):
    codice = 409


class GiroChiuso(ErroreServizio):
    codice = 410


class Telegram(Protocol):
    def scrivi(self, chat_id: int, testo: str) -> int: ...

    def manda_foto(self, chat_id: int, dati: bytes, didascalia: str, pulsanti: Pulsanti) -> int: ...

    def modifica_didascalia(
        self, chat_id: int, messaggio: int, testo: str, pulsanti: Pulsanti | None = None
    ) -> None: ...

    def chiedi_risposta(self, chat_id: int, testo: str) -> int: ...


class Notifiche(Protocol):
    def a_persona(self, soprannome: str, titolo: str, testo: str, *, ttl: int) -> int: ...


@dataclass(frozen=True)
class Ricevuta:
    foto: Foto
    messaggio_da_ritirare: int | None  # il messaggio del bot per la versione sostituita


def _iso(momento: datetime) -> str:
    return momento.astimezone(UTC).isoformat()


class Servizio:
    def __init__(
        self,
        *,
        store: Store,
        cartella_foto: Path,
        telegram: Telegram,
        notifiche: Notifiche,
        impostazioni: Impostazioni,
        chiave_vapid: str,
        ora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._cartella = cartella_foto
        self._telegram = telegram
        self._notifiche = notifiche
        self._imp = impostazioni
        self._chiave_vapid = chiave_vapid
        self._ora = ora

    # --- identità

    def persona(self, gettone: str) -> Persona | None:
        if not gettone:
            return None
        return self._store.persona_da_impronta(gettoni.impronta(gettone))

    def _richiedi(self, persona: Persona, ruoli: frozenset[str]) -> None:
        if persona.ruolo not in ruoli:
            raise NonTrovato("operazione inesistente")

    # --- giro

    def _giro_json(self, giro: Giro) -> dict:
        return {
            "id": giro.id,
            "aperto_alle": _iso(giro.aperto_alle),
            "scade_alle": _iso(regole.fine(giro)),
            "sessione": giro.sessione,
        }

    def _giro_aperto(self) -> Giro | None:
        giro = self._store.ultimo_giro()
        if giro is None or not regole.aperto(giro, self._ora()):
            return None
        return giro

    def _giro_aperto_da_id(self, giro_id: int) -> Giro:
        giro = self._store.giro(giro_id)
        if giro is None:
            raise NonTrovato("giro inesistente")
        if not regole.aperto(giro, self._ora()):
            raise GiroChiuso("il giro è chiuso")
        return giro

    def apri_giro(self, persona: Persona) -> dict:
        self._richiedi(persona, regole.CHI_APRE)
        ora = self._ora()
        decisione = regole.decidi_apertura(self._store.ultimo_giro(), ora)
        if decisione.riusa is not None:
            return {"giro": self._giro_json(decisione.riusa), "nuovo": False, "annuncio": None}
        if decisione.chiudi is not None:
            self._store.chiudi_giro(decisione.chiudi.id, ora)
        giro = self._store.crea_giro(ora, persona.soprannome)
        return {"giro": self._giro_json(giro), "nuovo": True, "annuncio": self._annuncia_nel_gruppo()}

    def _annuncia_nel_gruppo(self) -> dict:
        gruppo = "prova" if self._imp.sicura_inserita else "party"
        try:
            self._telegram.scrivi(self._imp.gruppo_annuncio, TESTO_INVITO_GRUPPO)
        except TelegramError as e:
            log.warning("annuncio nel gruppo non partito: %s", e)
            return {"esito": "fallito", "gruppo": gruppo}
        return {"esito": "inviato", "gruppo": gruppo}

    def invita(self, escluso: str) -> None:
        """Il push dell'invito a chi scatta, tranne chi ha aperto il giro."""
        for persona in self._store.persone():
            if persona.ruolo in regole.CHI_SCATTA and persona.soprannome != escluso:
                self._notifiche.a_persona(
                    persona.soprannome, TITOLO, TESTO_INVITO_PUSH, ttl=TTL_INVITO
                )

    # --- foto

    def ricevi_foto(self, persona: Persona, giro_id: int, dati: bytes) -> Ricevuta:
        self._richiedi(persona, regole.CHI_SCATTA)
        self._giro_aperto_da_id(giro_id)
        attuale = self._store.foto(giro_id, persona.soprannome)
        try:
            stato = regole.stato_dopo_invio(attuale.stato if attuale else None, persona.ruolo)
        except regole.RegolaViolata as e:
            raise Conflitto(str(e)) from e
        foto.valida(dati)
        temporaneo = foto.salva_temporaneo(self._cartella, giro_id, persona.soprannome, dati)
        try:
            nuova = self._store.salva_foto(
                giro_id, persona.soprannome, stato, foto.impronta(dati), len(dati), self._ora()
            )
            if nuova is None:
                raise Conflitto("la foto è già stata accettata: è definitiva")
            try:
                foto.promuovi(
                    temporaneo, self._cartella, giro_id, persona.soprannome, nuova.versione
                )
            except OSError:
                # Senza il file la riga racconterebbe una foto che non c'è:
                # torna com'era, e l'errore risale (la pagina riproverà).
                self._store.ripristina_foto(giro_id, persona.soprannome, nuova.versione, attuale)
                raise
        finally:
            temporaneo.unlink(missing_ok=True)
        if attuale is not None:
            foto.cancella(self._cartella, giro_id, persona.soprannome, attuale.versione)
        return Ricevuta(nuova, attuale.messaggio_bot if attuale else None)

    def _modifica(self, messaggio: int, testo: str, pulsanti_: Pulsanti | None = None) -> None:
        try:
            self._telegram.modifica_didascalia(
                self._imp.admin_telegram_id, messaggio, testo, pulsanti_
            )
        except TelegramError as e:
            log.warning("messaggio %s del bot non aggiornato: %s", messaggio, e)

    def annuncia_foto(
        self, giro_id: int, soprannome: str, versione: int, ritira: int | None
    ) -> None:
        """Manda ad Alberto la foto da validare, e ritira il messaggio della
        versione sostituita. Se nel frattempo la foto è cambiata o è stata
        decisa, non manda niente: il messaggio sarebbe vecchio."""
        if ritira is not None:
            self._modifica(ritira, f"↩️ Selfie di {soprannome}: sostituita da una foto nuova")
        corrente = self._store.foto(giro_id, soprannome)
        if corrente is None or corrente.versione != versione or corrente.stato != regole.IN_ATTESA:
            return
        dati = foto.leggi(self._cartella, giro_id, soprannome, versione)
        try:
            messaggio = self._telegram.manda_foto(
                self._imp.admin_telegram_id,
                dati,
                f"Selfie di {soprannome}",
                pulsanti.tastiera(giro_id, soprannome, versione, self._imp.motivi),
            )
        except TelegramError as e:
            log.warning("foto di %s non mandata ad Alberto: %s", soprannome, e)
            return
        self._store.imposta_messaggio_bot(giro_id, soprannome, versione, messaggio)

    def rinvia(self, persona: Persona, giro_id: int) -> datetime:
        self._richiedi(persona, regole.CHI_SCATTA)
        self._giro_aperto_da_id(giro_id)
        fino_a = regole.rinvio_fino_a(self._ora(), self._imp.rinvio_minuti)
        self._store.imposta_rinvio(giro_id, persona.soprannome, fino_a)
        return fino_a

    # --- stato per la pagina

    def stato(self, persona: Persona) -> dict:
        ora = self._ora()
        giro = self._giro_aperto()
        risposta: dict = {
            "persona": persona.soprannome,
            "ruolo": persona.ruolo,
            "ora": _iso(ora),
            "vapid": self._chiave_vapid,
            "giro": None,
            "foto": None,
            "rinvio_fino_a": None,
        }
        if giro is not None:
            risposta["giro"] = self._giro_json(giro)
            mia = self._store.foto(giro.id, persona.soprannome)
            if mia is not None:
                risposta["foto"] = {"stato": mia.stato, "sha256": mia.sha256, "motivo": mia.motivo}
            rinvio = self._store.rinvio(giro.id, persona.soprannome)
            if rinvio is not None and rinvio.fino_a > ora:
                risposta["rinvio_fino_a"] = _iso(rinvio.fino_a)
        if persona.ruolo in regole.CHI_APRE:
            risposta["pannello"] = self._pannello(giro, ora)
        return risposta

    def _pannello(self, giro: Giro | None, ora: datetime) -> list[dict]:
        righe = []
        for persona in self._store.persone():
            if persona.ruolo not in regole.CHI_SCATTA:
                continue
            stato_foto, rinvio_attivo = None, False
            if giro is not None:
                sua = self._store.foto(giro.id, persona.soprannome)
                stato_foto = sua.stato if sua else None
                rinvio = self._store.rinvio(giro.id, persona.soprannome)
                rinvio_attivo = rinvio is not None and rinvio.fino_a > ora
            righe.append(
                {
                    "soprannome": persona.soprannome,
                    "stato": regole.stato_pannello(stato_foto, rinvio_attivo),
                }
            )
        return righe
