"""I due cicli di fondo del servizio, ciascuno nel suo filo.

`ciclo_bot` legge il bot in long polling e passa ogni aggiornamento al
validatore. L'offset si salva dopo aver gestito l'aggiornamento: dopo un
riavvio si riparte da lì, e un aggiornamento gestito due volte è innocuo (la
seconda decisione trova la foto già decisa e lo dice).

`ciclo_pianificatore` manda i rinvii scaduti e fa pulizia, ogni 30 secondi.

Nessuno dei due si ferma per un errore: lo registra e continua. Si fermano
solo quando `fermo` è impostato, alla chiusura del servizio.
"""

from __future__ import annotations

import logging
import threading

from .telegram import TelegramError

log = logging.getLogger(__name__)

CHIAVE_OFFSET = "offset_bot"


def ciclo_bot(
    telegram,
    validatore,
    store,
    fermo: threading.Event,
    *,
    attesa: int = 25,
    pausa_errore: float = 5.0,
) -> None:
    salvato = store.leggi_valore(CHIAVE_OFFSET)
    offset = int(salvato) if salvato else None
    while not fermo.is_set():
        try:
            aggiornamenti = telegram.aggiornamenti(offset, attesa)
        except TelegramError as e:
            log.warning("lettura del bot non riuscita: %s", e)
            fermo.wait(pausa_errore)
            continue
        for aggiornamento in aggiornamenti:
            try:
                validatore.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            offset = int(aggiornamento["update_id"]) + 1
            store.scrivi_valore(CHIAVE_OFFSET, str(offset))


def passo(servizio) -> None:
    try:
        inviati = servizio.notifica_rinvii_scaduti()
        if inviati:
            log.info("rinvii notificati: %s", inviati)
    except Exception:
        log.exception("rinvii scaduti non gestiti")
    try:
        puliti = servizio.pulisci()
        if puliti:
            log.info("giri ripuliti delle foto: %s", puliti)
    except Exception:
        log.exception("pulizia non riuscita")


def ciclo_pianificatore(servizio, fermo: threading.Event, *, intervallo: float = 30.0) -> None:
    while not fermo.wait(intervallo):
        passo(servizio)
