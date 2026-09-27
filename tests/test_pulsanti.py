import pytest

from rsm import pulsanti
from rsm.config import MOTIVI_PREDEFINITI


def test_andata_e_ritorno():
    dati = pulsanti.dati_tocco(12, "jean-paul", 3, "m1")
    assert pulsanti.leggi_tocco(dati) == pulsanti.Tocco(12, "jean-paul", 3, "m1")


def test_il_caso_peggiore_sta_nei_64_byte_di_telegram():
    assert len(pulsanti.dati_tocco(999999, "x" * 32, 9999, "altro").encode()) <= 64


@pytest.mark.parametrize("dati", ["", "x|1|emi|1|ok", "v|uno|emi|1|ok", "v|1|../x|1|ok", "v|1|emi|1"])
def test_dati_estranei_non_si_leggono(dati):
    assert pulsanti.leggi_tocco(dati) is None


def test_la_tastiera():
    righe = pulsanti.tastiera(1, "emi", 2, MOTIVI_PREDEFINITI)
    testi = [[testo for testo, _ in riga] for riga in righe]
    assert testi == [
        ["✅ Va bene"],
        ["Sfocata", "Troppo buia"],
        ["Viso non inquadrato", "Tagliata"],
        ["✏️ Altro motivo…", "🔄 Un'altra, senza motivo"],
    ]
    assert righe[1][1][1] == "v|1|emi|2|m1"


def test_il_motivo_del_pulsante():
    assert pulsanti.motivo_del_pulsante("m1", MOTIVI_PREDEFINITI) == "troppo buia"
    assert pulsanti.motivo_del_pulsante("m9", MOTIVI_PREDEFINITI) is None
    assert pulsanti.motivo_del_pulsante("ok", MOTIVI_PREDEFINITI) is None
    assert pulsanti.motivo_del_pulsante("mx", MOTIVI_PREDEFINITI) is None
