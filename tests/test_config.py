import json

import pytest

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


def test_il_contatto_vapid_deve_essere_mailto_o_https():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_VAPID_CONTATTO"):
        config.da_ambiente({**AMBIENTE, "RSM_VAPID_CONTATTO": "qualcuno@example.org"})


def test_il_rinvio_deve_durare_almeno_un_minuto():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_RINVIO_MINUTI"):
        config.da_ambiente({**AMBIENTE, "RSM_RINVIO_MINUTI": "0"})


def test_url_base():
    assert config.url_base({"RSM_URL_BASE": "https://selfie.example.org/"}) == "https://selfie.example.org"
    assert config.url_base({"RSM_URL_BASE": "http://127.0.0.1:8000"}) == "http://127.0.0.1:8000"
    with pytest.raises(config.ConfigurazioneErrata, match="https"):
        config.url_base({"RSM_URL_BASE": "http://selfie.example.org"})
