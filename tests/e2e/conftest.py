"""Il servizio vero, con Telegram e push finti, su una porta locale; e Chrome con
la webcam finta. 127.0.0.1 per il browser è un contesto sicuro: fotocamera,
service worker e crypto.subtle funzionano come in HTTPS."""

import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import uvicorn

from rsm import gettoni
from rsm.app import crea_app
from rsm.servizio import Servizio
from rsm.store import Store
from tests.finti import NotificheFinte, TelegramFinto, impostazioni_di_prova

CARTELLA_WEB = Path(__file__).resolve().parents[2] / "web"


def _porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def in_rete(tmp_path):
    imp = impostazioni_di_prova(tmp_path)
    store = Store(imp.db)
    store.crea_schema()
    telegram = TelegramFinto()
    servizio = Servizio(
        store=store, cartella_foto=imp.cartella_foto, telegram=telegram,
        notifiche=NotificheFinte(), impostazioni=imp, chiave_vapid="BAAA",
    )
    gettone_emi, gettone_gio = gettoni.genera(), gettoni.genera()
    store.aggiungi_persona("emi", "giocatore", gettoni.impronta(gettone_emi))
    store.aggiungi_persona("gio", "master", gettoni.impronta(gettone_gio))
    porta = _porta_libera()
    server = uvicorn.Server(
        uvicorn.Config(crea_app(servizio, cartella_web=CARTELLA_WEB), host="127.0.0.1", port=porta, log_level="warning")
    )
    filo = threading.Thread(target=server.run, daemon=True)
    filo.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield SimpleNamespace(
        url=f"http://127.0.0.1:{porta}",
        servizio=servizio,
        store=store,
        telegram=telegram,
        emi=gettone_emi,
        gio=store.persona_da_impronta(gettoni.impronta(gettone_gio)),
    )
    server.should_exit = True
    filo.join(timeout=5)


@pytest.fixture
def pagina():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        )
        yield browser.new_page()
        browser.close()
