"""La politica del bot: cosa fare di un tocco su un pulsante e di un messaggio.

Solo Alberto decide. Ogni tocco riceve una risposta (Telegram altrimenti lascia
il pulsante in attesa), e la risposta dice la verità: «Accettata» solo se la
decisione è stata registrata, altrimenti il motivo per cui non lo è.

Un motivo scritto è una risposta alla domanda del bot: si riconosce dal testo
della domanda a cui risponde, così un messaggio qualsiasi di Alberto al bot non
viene preso per un motivo.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from . import pulsanti, regole
from .config import Motivo
from .servizio import ErroreServizio, RichiestaErrata, Servizio
from .telegram import TelegramError

log = logging.getLogger(__name__)


class Validatore:
    def __init__(
        self, servizio: Servizio, telegram, admin_telegram_id: int, motivi: Sequence[Motivo]
    ) -> None:
        self._servizio = servizio
        self._telegram = telegram
        self._admin = admin_telegram_id
        self._motivi = motivi

    def gestisci(self, aggiornamento: dict) -> None:
        if "callback_query" in aggiornamento:
            self._tocco(aggiornamento["callback_query"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])

    def _rispondi(self, tocco_id: str, testo: str) -> None:
        try:
            self._telegram.rispondi_tocco(tocco_id, testo)
        except TelegramError as e:
            log.warning("risposta al tocco non partita: %s", e)

    def _esito(self, azione: str) -> tuple[str, str | None]:
        if azione == pulsanti.ACCETTA:
            return regole.ACCETTATA, None
        if azione == pulsanti.SENZA_MOTIVO:
            return regole.DA_RIFARE, None
        motivo = pulsanti.motivo_del_pulsante(azione, self._motivi)
        if motivo is None:
            raise RichiestaErrata("Pulsante sconosciuto")
        return regole.DA_RIFARE, motivo

    def _tocco(self, dati: dict) -> None:
        tocco_id = dati.get("id", "")
        if dati.get("from", {}).get("id") != self._admin:
            self._rispondi(tocco_id, "Solo Alberto può decidere")
            return
        tocco = pulsanti.leggi_tocco(dati.get("data") or "")
        if tocco is None:
            self._rispondi(tocco_id, "Pulsante sconosciuto")
            return
        if tocco.azione == pulsanti.ALTRO:
            try:
                self._servizio.aspetta_motivo(tocco.giro_id, tocco.soprannome, tocco.versione)
            except ErroreServizio as e:
                self._rispondi(tocco_id, str(e))
            except TelegramError as e:
                log.warning("domanda del motivo non partita: %s", e)
                self._rispondi(tocco_id, "Telegram non ha risposto: riprova")
            else:
                self._rispondi(tocco_id, "Scrivi il motivo rispondendo alla domanda")
            return
        try:
            esito, motivo = self._esito(tocco.azione)
            decisa = self._servizio.decidi(
                tocco.giro_id, tocco.soprannome, tocco.versione, esito, motivo
            )
        except ErroreServizio as e:
            self._rispondi(tocco_id, str(e))
            return
        self._rispondi(tocco_id, "Accettata" if esito == regole.ACCETTATA else "Chiesta un'altra foto")
        self._servizio.dopo_decisione(decisa)

    def _messaggio(self, messaggio: dict) -> None:
        if messaggio.get("from", {}).get("id") != self._admin:
            return
        domanda = messaggio.get("reply_to_message") or {}
        if not (domanda.get("text") or "").startswith(pulsanti.DOMANDA_MOTIVO):
            return
        try:
            decisa = self._servizio.motivo_scritto(domanda["message_id"], messaggio.get("text"))
        except regole.RegolaViolata as e:
            self._scrivi_ad_alberto(f"Non va: {e}. Riscrivilo rispondendo alla stessa domanda.")
            return
        except ErroreServizio as e:
            self._scrivi_ad_alberto(str(e))
            return
        if decisa is None:
            self._scrivi_ad_alberto(
                "Nel frattempo quella foto è stata sostituita o già decisa: il motivo non serve più."
            )
            return
        self._servizio.dopo_decisione(decisa)

    def _scrivi_ad_alberto(self, testo: str) -> None:
        try:
            self._telegram.scrivi(self._admin, testo)
        except TelegramError as e:
            log.warning("messaggio ad Alberto non partito: %s", e)
