"""Il bot vero. Si può lanciare con il servizio acceso: questi test scrivono e
basta, e scrivere non ruba gli aggiornamenti al ciclo del servizio."""

import pytest

from rsm import pulsanti
from rsm.config import MOTIVI_PREDEFINITI
from rsm.telegram import BotTelegram
from tests.immagini import jpeg
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def bot():
    return BotTelegram(richiesta("RSM_BOT_TOKEN"))


def test_nessun_webhook_quindi_il_long_polling_funziona():
    assert bot().webhook_attivo() is False


def test_scrive_nel_gruppo_di_prova():
    gruppo = int(richiesta("RSM_GRUPPO_PROVA"))
    messaggio = bot().scrivi(gruppo, "🧪 Prova del piano reale di Radiant Selfie Machine: ignorate.")
    assert isinstance(messaggio, int)


def test_manda_ad_alberto_una_foto_con_i_pulsanti_e_la_modifica():
    """Contratto: Alberto ha scritto /start al bot, sendPhoto in multipart con la
    tastiera funziona, e editMessageCaption toglie i pulsanti."""
    alberto = int(richiesta("RSM_ADMIN_TELEGRAM_ID"))
    b = bot()
    messaggio = b.manda_foto(
        alberto,
        jpeg(640, 480),
        "🧪 Prova del piano reale: ignora i pulsanti",
        pulsanti.tastiera(0, "prova", 1, MOTIVI_PREDEFINITI),
    )
    b.modifica_didascalia(alberto, messaggio, "🧪 Prova del piano reale: conclusa")
