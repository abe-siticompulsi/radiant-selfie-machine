"""Le notifiche Web Push: l'invito, il rinvio, l'esito della validazione.

Due trappole del vero, entrambe in docs/differenze-fra-test-e-realta.md:
- `pywebpush.webpush` scrive dentro `vapid_claims` l'«aud» del primo servizio
  push che incontra: riusare lo stesso dizionario per un'iscrizione di Firefox
  dopo una di Chrome firmerebbe per il destinatario sbagliato (403). Un
  dizionario nuovo a ogni invio.
- il TTL predefinito è 0: un telefono spento perderebbe la notifica. Il TTL lo
  sceglie sempre chi chiama.

Un invio fallito non fa mai fallire l'operazione che l'ha causato: si registra
e si va avanti. Il gruppo Telegram e il polling della pagina restano.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import requests
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid01, b64urlencode
from pywebpush import WebPushException, webpush

from .store import Store

log = logging.getLogger(__name__)

_SCADUTA = (404, 410)


def chiave_pubblica(vapid: Vapid01) -> str:
    """La chiave che la pagina passa a `pushManager.subscribe`."""
    return b64urlencode(
        vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    )


class Notificatore:
    def __init__(
        self,
        store: Store,
        vapid: Vapid01,
        contatto: str,
        invia: Callable[..., Any] = webpush,
    ) -> None:
        self._store = store
        self._vapid = vapid
        self._contatto = contatto
        self._invia = invia

    def a_persona(self, soprannome: str, titolo: str, testo: str, *, ttl: int) -> int:
        """Manda la notifica a tutti i dispositivi iscritti di una persona.

        Restituisce quanti invii il servizio push ha accettato: accettato non
        vuol dire consegnato.
        """
        dati = json.dumps({"titolo": titolo, "testo": testo})
        accettati = 0
        for iscrizione in self._store.iscrizioni_di(soprannome):
            try:
                self._invia(
                    subscription_info={
                        "endpoint": iscrizione.endpoint,
                        "keys": {"p256dh": iscrizione.p256dh, "auth": iscrizione.auth},
                    },
                    data=dati,
                    vapid_private_key=self._vapid,
                    vapid_claims={"sub": self._contatto},
                    ttl=ttl,
                    timeout=10,
                )
            except WebPushException as e:
                stato = getattr(e.response, "status_code", None)
                if stato in _SCADUTA:
                    self._store.togli_iscrizione(iscrizione.endpoint)
                    log.info("iscrizione push di %s scaduta (%s): tolta", soprannome, stato)
                else:
                    log.warning("push a %s rifiutato dal servizio push (%s)", soprannome, stato)
            except (requests.RequestException, OSError) as e:
                log.warning("push a %s non inviato: %s", soprannome, type(e).__name__)
            else:
                accettati += 1
        return accettati
