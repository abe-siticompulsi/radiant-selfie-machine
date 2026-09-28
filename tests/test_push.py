import base64
import json

import pytest
import requests
from py_vapid import Vapid
from pywebpush import WebPushException

from rsm.push import Notificatore, chiave_pubblica
from rsm.store import Iscrizione


class Risposta:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""
        self.headers = {}


@pytest.fixture
def vapid():
    chiave = Vapid()
    chiave.generate_keys()
    return chiave


@pytest.fixture
def con_iscrizioni(store):
    store.aggiungi_iscrizione(Iscrizione("https://fcm.googleapis.com/fcm/send/a", "emi", "p1", "a1"))
    store.aggiungi_iscrizione(Iscrizione("https://updates.push.services.mozilla.com/b", "emi", "p2", "a2"))
    store.aggiungi_iscrizione(Iscrizione("https://fcm.googleapis.com/fcm/send/c", "gio", "p3", "a3"))
    return store


def test_manda_a_ogni_iscrizione_della_persona(con_iscrizioni, vapid):
    chiamate = []
    n = Notificatore(con_iscrizioni, vapid, "mailto:prova@example.org", invia=lambda **kw: chiamate.append(kw))
    assert n.a_persona("emi", "📸 Selfie", "È il momento del selfie!", ttl=1800) == 2
    assert [c["subscription_info"]["endpoint"] for c in chiamate] == [
        "https://fcm.googleapis.com/fcm/send/a",
        "https://updates.push.services.mozilla.com/b",
    ]
    assert chiamate[0]["subscription_info"]["keys"] == {"p256dh": "p1", "auth": "a1"}
    assert all(c["ttl"] == 1800 for c in chiamate)
    assert all(c["vapid_private_key"] is vapid for c in chiamate)
    assert json.loads(chiamate[0]["data"]) == {"titolo": "📸 Selfie", "testo": "È il momento del selfie!"}


def test_i_claims_sono_nuovi_a_ogni_invio(con_iscrizioni, vapid):
    """webpush scrive l'«aud» del primo servizio push dentro vapid_claims: se il
    dizionario fosse lo stesso, il secondo invio firmerebbe per Google una
    richiesta destinata a Mozilla, e Mozilla risponderebbe 403."""
    visti = []

    def invia_che_modifica(**kw):
        visti.append(dict(kw["vapid_claims"]))
        kw["vapid_claims"]["aud"] = kw["subscription_info"]["endpoint"]

    Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia_che_modifica).a_persona(
        "emi", "t", "x", ttl=60
    )
    assert visti == [{"sub": "mailto:a@b.c"}, {"sub": "mailto:a@b.c"}]


@pytest.mark.parametrize("stato", [404, 410])
def test_un_iscrizione_scaduta_viene_tolta(con_iscrizioni, vapid, stato):
    def invia(**kw):
        raise WebPushException("scaduta", response=Risposta(stato))

    assert Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia).a_persona("gio", "t", "x", ttl=60) == 0
    assert con_iscrizioni.iscrizioni_di("gio") == []


def test_un_altro_rifiuto_non_toglie_l_iscrizione(con_iscrizioni, vapid):
    def invia(**kw):
        raise WebPushException("errore", response=Risposta(500))

    assert Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia).a_persona("gio", "t", "x", ttl=60) == 0
    assert len(con_iscrizioni.iscrizioni_di("gio")) == 1


def test_un_errore_di_rete_non_esplode(con_iscrizioni, vapid):
    def invia(**kw):
        raise requests.ConnectionError("rete giù")

    assert Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia).a_persona("gio", "t", "x", ttl=60) == 0


@pytest.mark.parametrize("errore", [ValueError("Invalid EC key"), IndexError("index out of range")])
def test_una_chiave_malformata_non_esplode_e_non_ferma_gli_altri_dispositivi(con_iscrizioni, vapid, errore, caplog):
    """pywebpush solleva così su una chiave che non è un punto P-256: il push
    agli altri dispositivi parte lo stesso, e l'iscrizione resta (non è scaduta)."""
    tentati = []

    def invia(**kw):
        tentati.append(kw["subscription_info"]["endpoint"])
        if len(tentati) == 1:
            raise errore

    notificatore = Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia)
    assert notificatore.a_persona("emi", "t", "x", ttl=60) == 1
    assert len(tentati) == 2
    assert len(con_iscrizioni.iscrizioni_di("emi")) == 2
    assert type(errore).__name__ in caplog.text
    assert str(errore) not in caplog.text


def test_senza_iscrizioni_non_si_manda_niente(store, vapid):
    chiamate = []
    n = Notificatore(store, vapid, "mailto:a@b.c", invia=lambda **kw: chiamate.append(kw))
    assert n.a_persona("nessuno", "t", "x", ttl=60) == 0
    assert chiamate == []


def test_la_chiave_pubblica_e_un_punto_non_compresso(vapid):
    chiave = chiave_pubblica(vapid)
    assert len(chiave) == 87
    grezza = base64.urlsafe_b64decode(chiave + "=")
    assert len(grezza) == 65 and grezza[0] == 4
