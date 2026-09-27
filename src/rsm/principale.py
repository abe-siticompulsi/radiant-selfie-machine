"""Il punto d'ingresso: costruisce il servizio vero dall'ambiente.

    uvicorn --factory rsm.principale:costruisci --no-access-log

Il log d'accesso di uvicorn resta spento: scriverebbe il percorso di ogni
richiesta, e il percorso della pagina contiene il gettone. Il logger `httpx`
sta a WARNING per lo stesso motivo: al livello INFO scriverebbe l'URL di ogni
chiamata a Telegram, token compreso.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from py_vapid import Vapid

from . import cicli, config
from .app import crea_app
from .push import Notificatore, chiave_pubblica
from .servizio import Servizio
from .store import Store
from .telegram import BotTelegram
from .validazione import Validatore

CARTELLA_WEB = Path(__file__).resolve().parents[2] / "web"


def costruisci(env: Mapping[str, str] | None = None, *, avvia_cicli: bool = True) -> FastAPI:
    env = os.environ if env is None else env
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    imp = config.da_ambiente(env)
    imp.cartella_foto.mkdir(parents=True, exist_ok=True)
    store = Store(imp.db)
    store.crea_schema()
    vapid = Vapid.from_file(str(imp.vapid_pem))
    telegram = BotTelegram(imp.token_bot)
    servizio = Servizio(
        store=store,
        cartella_foto=imp.cartella_foto,
        telegram=telegram,
        notifiche=Notificatore(store, vapid, imp.vapid_contatto),
        impostazioni=imp,
        chiave_vapid=chiave_pubblica(vapid),
    )
    validatore = Validatore(servizio, telegram, imp.admin_telegram_id, imp.motivi)

    lifespan = None
    if avvia_cicli:

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            fermo = threading.Event()
            fili = [
                threading.Thread(
                    target=cicli.ciclo_bot,
                    args=(telegram, validatore, store, fermo),
                    name="bot",
                    daemon=True,
                ),
                threading.Thread(
                    target=cicli.ciclo_pianificatore,
                    args=(servizio, fermo),
                    name="pianificatore",
                    daemon=True,
                ),
            ]
            for filo in fili:
                filo.start()
            try:
                yield
            finally:
                fermo.set()

    cartella_web = Path(env.get("RSM_WEB") or CARTELLA_WEB)
    return crea_app(servizio, cartella_web=cartella_web, lifespan=lifespan)
