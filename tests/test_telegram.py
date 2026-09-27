import json

import httpx
import pytest

from rsm.telegram import BotTelegram, TelegramError
from tests.immagini import jpeg

TOKEN = "123:SEGRETO"


def bot_con(gestore):
    return BotTelegram(TOKEN, http=httpx.Client(transport=httpx.MockTransport(gestore)))


def ok(risultato):
    return httpx.Response(200, json={"ok": True, "result": risultato})


def registra(risultato):
    viste = []

    def gestore(richiesta):
        viste.append(richiesta)
        return ok(risultato)

    return viste, gestore


def test_scrivi_manda_testo_semplice_e_restituisce_l_id():
    viste, gestore = registra({"message_id": 42})
    assert bot_con(gestore).scrivi(-100, "ciao *non* markdown") == 42
    assert viste[0].url.path == f"/bot{TOKEN}/sendMessage"
    # niente parse_mode: il motivo scritto da Alberto è testo semplice
    assert json.loads(viste[0].content) == {"chat_id": -100, "text": "ciao *non* markdown"}


def test_manda_foto_in_multipart_con_i_pulsanti():
    viste, gestore = registra({"message_id": 7})
    dati = jpeg()
    pulsanti = [[("✅ Va bene", "v|1|emi|1|ok")], [("Sfocata", "v|1|emi|1|m0")]]
    assert bot_con(gestore).manda_foto(123456789, dati, "Selfie di emi", pulsanti) == 7
    corpo = viste[0].content
    assert viste[0].url.path.endswith("/sendPhoto")
    assert dati in corpo
    assert b'filename="selfie.jpg"' in corpo
    assert b'"callback_data": "v|1|emi|1|ok"' in corpo
    assert b"Selfie di emi" in corpo


def test_modifica_didascalia_senza_pulsanti_li_toglie():
    viste, gestore = registra(True)
    bot_con(gestore).modifica_didascalia(123456789, 7, "✅ accettata")
    corpo = json.loads(viste[0].content)
    assert corpo == {
        "chat_id": 123456789,
        "message_id": 7,
        "caption": "✅ accettata",
        "reply_markup": {"inline_keyboard": []},
    }


def test_modifica_didascalia_con_pulsanti_li_tiene():
    viste, gestore = registra(True)
    bot_con(gestore).modifica_didascalia(1, 7, "attendo", [[("✅ Va bene", "v|1|emi|1|ok")]])
    tastiera = json.loads(viste[0].content)["reply_markup"]["inline_keyboard"]
    assert tastiera == [[{"text": "✅ Va bene", "callback_data": "v|1|emi|1|ok"}]]


def test_chiedi_risposta_usa_force_reply():
    viste, gestore = registra({"message_id": 900})
    assert bot_con(gestore).chiedi_risposta(1, "Scrivi il motivo per emi") == 900
    corpo = json.loads(viste[0].content)
    assert corpo["reply_markup"]["force_reply"] is True


def test_rispondi_tocco_accorcia_a_200_caratteri():
    viste, gestore = registra(True)
    bot_con(gestore).rispondi_tocco("t1", "x" * 250)
    assert json.loads(viste[0].content) == {"callback_query_id": "t1", "text": "x" * 200}


def test_aggiornamenti_passa_offset_e_attesa():
    viste, gestore = registra([{"update_id": 5}])
    bot = bot_con(gestore)
    assert bot.aggiornamenti(7, 25) == [{"update_id": 5}]
    assert json.loads(viste[0].content) == {
        "timeout": 25,
        "allowed_updates": ["message", "callback_query"],
        "offset": 7,
    }
    bot.aggiornamenti(None, 0)
    assert "offset" not in json.loads(viste[1].content)


def test_webhook_attivo():
    assert bot_con(lambda r: ok({"url": ""})).webhook_attivo() is False
    assert bot_con(lambda r: ok({"url": "https://altrove"})).webhook_attivo() is True


def test_un_rifiuto_dell_api_diventa_telegram_error():
    def gestore(richiesta):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(TelegramError, match="sendMessage: Bad Request: chat not found"):
        bot_con(gestore).scrivi(1, "x")


def test_un_errore_di_rete_non_rivela_il_token():
    def gestore(richiesta):
        raise httpx.ConnectError(f"impossibile raggiungere {richiesta.url}", request=richiesta)

    with pytest.raises(TelegramError) as errore:
        bot_con(gestore).scrivi(1, "x")
    assert "SEGRETO" not in str(errore.value)
    assert errore.value.__cause__ is None
    assert errore.value.__suppress_context__


def test_una_risposta_non_json():
    with pytest.raises(TelegramError, match="HTTP 502"):
        bot_con(lambda r: httpx.Response(502, text="Bad gateway")).scrivi(1, "x")
