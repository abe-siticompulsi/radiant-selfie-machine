import json

import pytest
from py_vapid import Vapid01

from rsm import config

AMBIENTE = {
    "RSM_DB": "/data/rsm.sqlite",
    "RSM_FOTO": "/data/foto",
    "RSM_BOT_TOKEN": "123:abc",
    "RSM_GRUPPO_PROVA": "-4000",
    "RSM_GRUPPO": "",
    "RSM_ADMIN_TELEGRAM_ID": "123456789",
    "RSM_VAPID_PEM": "/config/vapid.pem",
    "RSM_VAPID_CONTATTO": "mailto:qualcuno@example.org",
}


def test_ambiente_completo_con_la_sicura_inserita():
    imp = config.da_ambiente(AMBIENTE)
    assert imp.sicura_inserita
    assert imp.gruppo_annuncio == -4000
    assert imp.rinvio_minuti == 10
    assert str(imp.db) == "/data/rsm.sqlite"
    assert imp.admin_telegram_id == 123456789


def test_con_il_party_la_sicura_e_armata():
    imp = config.da_ambiente({**AMBIENTE, "RSM_GRUPPO": "-987654321"})
    assert not imp.sicura_inserita
    assert imp.gruppo_annuncio == -987654321


def test_i_quattro_motivi_predefiniti():
    motivi = config.da_ambiente(AMBIENTE).motivi
    assert [m.etichetta for m in motivi] == ["Sfocata", "Troppo buia", "Viso non inquadrato", "Tagliata"]
    assert motivi[3].testo == "tagliata (controlla che tutta la testa sia ben visibile nella foto)"


def test_motivi_personalizzati():
    grezzi = json.dumps([{"etichetta": "Mossa", "testo": "mossa"}])
    assert config.da_ambiente({**AMBIENTE, "RSM_MOTIVI": grezzi}).motivi == (config.Motivo("Mossa", "mossa"),)


@pytest.mark.parametrize(
    "grezzi",
    ["non json", "[]", json.dumps([{"etichetta": "x"}]), json.dumps([{"etichetta": "", "testo": "x"}])],
)
def test_motivi_malformati(grezzi):
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_MOTIVI"):
        config.da_ambiente({**AMBIENTE, "RSM_MOTIVI": grezzi})


@pytest.mark.parametrize("nome", ["RSM_DB", "RSM_BOT_TOKEN", "RSM_GRUPPO_PROVA", "RSM_ADMIN_TELEGRAM_ID"])
def test_una_variabile_mancante_si_nomina(nome):
    with pytest.raises(config.ConfigurazioneErrata, match=nome):
        config.da_ambiente({**AMBIENTE, nome: ""})


def test_un_gruppo_non_numerico():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_GRUPPO_PROVA"):
        config.da_ambiente({**AMBIENTE, "RSM_GRUPPO_PROVA": "gruppo"})


CONTATTI_SBAGLIATI = [
    "qualcuno@example.org",
    "mailto:",
    "mailto:qualcuno",
    "mailto:qualcuno@",
    "mailto:qualcuno@example",
    "https://",
    "http://example.org",
    "https://example.org/contatti",
    "https://example.org/",
    "https://github.com/abe-siticompulsi/radiant-selfie-machine",
]
CONTATTI_GIUSTI = [
    "mailto:qualcuno@example.org",
    "mailto:12345+qualcuno@users.noreply.github.com",
    "https://example.org",
    "https://selfie.esempio.duckdns.org",
]


@pytest.mark.parametrize("contatto", CONTATTI_SBAGLIATI)
def test_il_contatto_vapid_deve_essere_un_indirizzo_vero(contatto):
    """Il valore dell'esempio, «mailto:», non passa, e nemmeno un https con un
    percorso: py_vapid lo rifiuta, e ogni push fallirebbe a servizio acceso."""
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_VAPID_CONTATTO"):
        config.da_ambiente({**AMBIENTE, "RSM_VAPID_CONTATTO": contatto})


@pytest.mark.parametrize("contatto", CONTATTI_GIUSTI)
def test_contatti_vapid_validi(contatto):
    assert config.da_ambiente({**AMBIENTE, "RSM_VAPID_CONTATTO": contatto}).vapid_contatto == contatto


@pytest.mark.parametrize("contatto", CONTATTI_SBAGLIATI + CONTATTI_GIUSTI)
def test_un_contatto_che_la_configurazione_accetta_lo_accetta_anche_py_vapid(contatto):
    """Chi firma è py_vapid: la configurazione non deve mai essere più larga di lui."""
    try:
        config.da_ambiente({**AMBIENTE, "RSM_VAPID_CONTATTO": contatto})
    except config.ConfigurazioneErrata:
        return
    vapid = Vapid01()
    vapid.generate_keys()
    vapid.sign({"sub": contatto, "aud": "https://updates.push.services.mozilla.com"})


def test_il_rinvio_deve_durare_almeno_un_minuto():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_RINVIO_MINUTI"):
        config.da_ambiente({**AMBIENTE, "RSM_RINVIO_MINUTI": "0"})


def test_url_base():
    assert config.url_base({"RSM_URL_BASE": "https://selfie.example.org/"}) == "https://selfie.example.org"
    assert config.url_base({"RSM_URL_BASE": "http://127.0.0.1:8000"}) == "http://127.0.0.1:8000"
    with pytest.raises(config.ConfigurazioneErrata, match="https"):
        config.url_base({"RSM_URL_BASE": "http://selfie.example.org"})
