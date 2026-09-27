from datetime import UTC, datetime

import pytest

from rsm import gettoni
from rsm.servizio import Servizio
from rsm.store import Store
from tests.finti import NotificheFinte, Orologio, TelegramFinto, impostazioni_di_prova

INIZIO = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)
TAVOLO = [
    ("abe", "admin"),
    ("gio", "master"),
    ("emi", "giocatore"),
    ("sem", "giocatore"),
    ("ctc", "ctc"),
]


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "rsm.sqlite")
    s.crea_schema()
    return s


@pytest.fixture
def orologio():
    return Orologio(INIZIO)


@pytest.fixture
def telegram():
    return TelegramFinto()


@pytest.fixture
def notifiche():
    return NotificheFinte()


@pytest.fixture
def impostazioni(tmp_path):
    return impostazioni_di_prova(tmp_path)


@pytest.fixture
def servizio(store, telegram, notifiche, impostazioni, orologio):
    return Servizio(
        store=store,
        cartella_foto=impostazioni.cartella_foto,
        telegram=telegram,
        notifiche=notifiche,
        impostazioni=impostazioni,
        chiave_vapid="CHIAVE-PUBBLICA",
        ora=orologio,
    )


@pytest.fixture
def persone(store):
    """Il tavolo di prova: persone["emi"] è la coppia (Persona, gettone)."""
    tavolo = {}
    for soprannome, ruolo in TAVOLO:
        gettone = gettoni.genera()
        store.aggiungi_persona(soprannome, ruolo, gettoni.impronta(gettone))
        tavolo[soprannome] = (store.persona_da_impronta(gettoni.impronta(gettone)), gettone)
    return tavolo
