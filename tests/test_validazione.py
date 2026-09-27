import pytest

from rsm import pulsanti
from rsm.validazione import Validatore
from tests.finti import telegram_guasto
from tests.immagini import jpeg

ALBERTO = 123456789


@pytest.fixture
def validatore(servizio, telegram, impostazioni):
    return Validatore(servizio, telegram, impostazioni.admin_telegram_id, impostazioni.motivi)


@pytest.fixture
def giro_id(servizio, persone):
    """La foto di emi in attesa, annunciata ad Alberto (messaggio 102)."""
    giro = servizio.apri_giro(persone["gio"][0])["giro"]["id"]
    servizio.ricevi_foto(persone["emi"][0], giro, jpeg())
    servizio.annuncia_foto(giro, "emi", 1, None)
    return giro


def tocco(dati, da=ALBERTO):
    return {"update_id": 1, "callback_query": {"id": "t1", "from": {"id": da}, "data": dati}}


def risposta(testo, domanda, da=ALBERTO):
    return {
        "update_id": 2,
        "message": {
            "message_id": 900,
            "from": {"id": da},
            "text": testo,
            "reply_to_message": {"message_id": domanda["id"], "text": domanda["testo"]},
        },
    }


def ultima_domanda(telegram):
    return {"id": 103, "testo": telegram.di_tipo("chiedi_risposta")[-1]["testo"]}


def test_va_bene_accetta_e_avvisa(validatore, giro_id, store, telegram, notifiche):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA)))
    assert store.foto(giro_id, "emi").stato == "accettata"
    assert telegram.di_tipo("rispondi_tocco")[-1] == {"tocco_id": "t1", "testo": "Accettata"}
    assert notifiche.inviate[-1]["testo"] == "La tua foto è stata accettata"


def test_un_motivo_pronto_chiede_un_altra_foto_con_il_suo_testo(validatore, giro_id, store, notifiche):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, "m3")))
    foto_emi = store.foto(giro_id, "emi")
    assert foto_emi.stato == "da_rifare"
    assert foto_emi.motivo == "tagliata (controlla che tutta la testa sia ben visibile nella foto)"
    assert notifiche.inviate[-1]["testo"] == (
        "Alberto chiede un'altra foto: tagliata (controlla che tutta la testa sia ben visibile nella foto)"
    )


def test_un_altra_senza_motivo(validatore, giro_id, store, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.SENZA_MOTIVO)))
    assert (store.foto(giro_id, "emi").stato, store.foto(giro_id, "emi").motivo) == ("da_rifare", None)
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Chiesta un'altra foto"


def test_solo_alberto_decide(validatore, giro_id, store, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA), da=12345))
    assert store.foto(giro_id, "emi").stato == "in_attesa"
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Solo Alberto può decidere"


@pytest.mark.parametrize("dati", ["spazzatura", "v|1|emi|1|m9", "v|1|emi|1|boh"])
def test_pulsanti_sconosciuti(validatore, giro_id, store, telegram, dati):
    validatore.gestisci(tocco(dati.replace("v|1|", f"v|{giro_id}|")))
    assert store.foto(giro_id, "emi").stato == "in_attesa"
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Pulsante sconosciuto"


def test_un_tocco_su_una_foto_sostituita(validatore, servizio, persone, giro_id, store, telegram):
    servizio.ricevi_foto(persone["emi"][0], giro_id, jpeg())
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA)))
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"].startswith("foto sostituita")
    assert store.foto(giro_id, "emi").stato == "in_attesa"


def test_altro_motivo_poi_il_testo(validatore, giro_id, store, telegram, notifiche):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Scrivi il motivo rispondendo alla domanda"
    validatore.gestisci(risposta("hai gli occhi chiusi", ultima_domanda(telegram)))
    foto_emi = store.foto(giro_id, "emi")
    assert (foto_emi.stato, foto_emi.motivo) == ("da_rifare", "hai gli occhi chiusi")
    assert notifiche.inviate[-1]["testo"] == "Alberto chiede un'altra foto: hai gli occhi chiusi"


def test_un_motivo_troppo_lungo_si_riscrive(validatore, giro_id, store, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    domanda = ultima_domanda(telegram)
    validatore.gestisci(risposta("x" * 201, domanda))
    assert store.foto(giro_id, "emi").stato == "in_attesa"
    avviso = telegram.di_tipo("scrivi")[-1]
    assert avviso["chat_id"] == ALBERTO
    assert "al massimo 200" in avviso["testo"] and "Riscrivilo" in avviso["testo"]
    validatore.gestisci(risposta("mossa", domanda))
    assert store.foto(giro_id, "emi").motivo == "mossa"


def test_una_risposta_a_una_domanda_superata(validatore, giro_id, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    domanda = ultima_domanda(telegram)
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA)))
    validatore.gestisci(risposta("sfocata", domanda))
    assert telegram.di_tipo("scrivi")[-1]["testo"] == (
        "Nel frattempo quella foto è stata sostituita o già decisa: il motivo non serve più."
    )


def test_i_messaggi_che_non_rispondono_alla_domanda_si_ignorano(validatore, giro_id, telegram):
    prima = len(telegram.chiamate)
    validatore.gestisci({"update_id": 3, "message": {"message_id": 1, "from": {"id": ALBERTO}, "text": "ciao"}})
    validatore.gestisci(risposta("x", {"id": 102, "testo": "Selfie di emi"}))
    validatore.gestisci(risposta("x", {"id": 103, "testo": "Scrivi il motivo per emi"}, da=12345))
    assert len(telegram.chiamate) == prima


def test_se_telegram_non_risponde_alla_richiesta_del_motivo(validatore, giro_id, telegram, store):
    telegram.guasto = telegram_guasto()
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    assert store.foto(giro_id, "emi").attesa_motivo is None
