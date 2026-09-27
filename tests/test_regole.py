from datetime import UTC, datetime, timedelta

import pytest

from rsm import regole
from rsm.regole import Giro

T0 = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)


def giro(aperto_alle=T0, chiuso_alle=None):
    return Giro(id=1, aperto_alle=aperto_alle, aperto_da="gio", chiuso_alle=chiuso_alle)


def test_un_giro_resta_aperto_48_ore_esatte():
    g = giro()
    assert regole.aperto(g, T0 + timedelta(hours=48) - timedelta(microseconds=1))
    assert not regole.aperto(g, T0 + timedelta(hours=48))


def test_un_giro_chiuso_prima_della_scadenza_finisce_alla_chiusura():
    g = giro(chiuso_alle=T0 + timedelta(hours=13))
    assert regole.fine(g) == T0 + timedelta(hours=13)
    assert not regole.aperto(g, T0 + timedelta(hours=13))


def test_senza_giri_si_apre_un_giro_nuovo():
    assert regole.decidi_apertura(None, T0) == regole.Apertura(riusa=None, chiudi=None)


def test_sotto_le_12_ore_si_riusa_il_giro_aperto():
    g = giro()
    decisione = regole.decidi_apertura(g, T0 + timedelta(hours=11, minutes=59))
    assert decisione == regole.Apertura(riusa=g, chiudi=None)


def test_dalle_12_ore_si_chiude_il_vecchio_e_se_ne_apre_uno_nuovo():
    g = giro()
    decisione = regole.decidi_apertura(g, T0 + timedelta(hours=12))
    assert decisione == regole.Apertura(riusa=None, chiudi=g)


def test_un_giro_gia_scaduto_non_va_chiuso_di_nuovo():
    decisione = regole.decidi_apertura(giro(), T0 + timedelta(hours=49))
    assert decisione == regole.Apertura(riusa=None, chiudi=None)


@pytest.mark.parametrize("ruolo", ["giocatore", "master"])
@pytest.mark.parametrize("attuale", [None, "in_attesa", "da_rifare"])
def test_la_foto_di_chi_gioca_va_in_attesa(ruolo, attuale):
    assert regole.stato_dopo_invio(attuale, ruolo) == "in_attesa"


def test_la_foto_di_alberto_e_accettata_all_arrivo():
    assert regole.stato_dopo_invio(None, "admin") == "accettata"


def test_una_foto_accettata_e_definitiva():
    with pytest.raises(regole.RegolaViolata, match="definitiva"):
        regole.stato_dopo_invio("accettata", "giocatore")


def test_ctc_non_scatta():
    with pytest.raises(regole.RegolaViolata, match="non scatta"):
        regole.stato_dopo_invio(None, "ctc")


def test_un_esito_sconosciuto_e_rifiutato():
    with pytest.raises(regole.RegolaViolata, match="sconosciuto"):
        regole.verifica_esito("forse", None)


def test_il_motivo_accompagna_solo_la_richiesta_di_un_altra_foto():
    with pytest.raises(regole.RegolaViolata, match="solo la richiesta"):
        regole.verifica_esito("accettata", "sfocata")


def test_il_motivo_si_ripulisce_e_si_restituisce():
    assert regole.verifica_esito("da_rifare", "  troppo buia ") == "troppo buia"
    assert regole.verifica_esito("da_rifare", None) is None
    assert regole.verifica_esito("accettata", None) is None


def test_un_motivo_vuoto_o_troppo_lungo_e_rifiutato():
    with pytest.raises(regole.RegolaViolata, match="vuoto"):
        regole.motivo_valido("   ")
    assert regole.motivo_valido("x" * 200) == "x" * 200
    with pytest.raises(regole.RegolaViolata, match="201 caratteri"):
        regole.motivo_valido("x" * 201)


def test_il_rinvio_dura_i_minuti_richiesti():
    assert regole.rinvio_fino_a(T0, 10) == T0 + timedelta(minutes=10)


def test_un_rinvio_si_notifica_una_volta_sola_e_solo_a_chi_non_ha_una_foto():
    fino_a = T0 + timedelta(minutes=10)
    assert not regole.rinvio_da_notificare(fino_a, False, None, fino_a - timedelta(seconds=1))
    assert regole.rinvio_da_notificare(fino_a, False, None, fino_a)
    assert regole.rinvio_da_notificare(fino_a, False, "da_rifare", fino_a)
    assert not regole.rinvio_da_notificare(fino_a, True, None, fino_a)
    assert not regole.rinvio_da_notificare(fino_a, False, "in_attesa", fino_a)
    assert not regole.rinvio_da_notificare(fino_a, False, "accettata", fino_a)


def test_le_foto_si_cancellano_30_giorni_dopo_la_fine_del_giro():
    g = giro()
    fine = T0 + timedelta(hours=48)
    assert not regole.da_cancellare(g, fine + timedelta(days=30) - timedelta(seconds=1))
    assert regole.da_cancellare(g, fine + timedelta(days=30))


@pytest.mark.parametrize("buono", ["emi", "jean-paul", "a_1", "x" * 32])
def test_soprannomi_ammessi(buono):
    assert regole.soprannome_valido(buono) == buono


@pytest.mark.parametrize("cattivo", ["", "Emi", "../x", "x" * 33, "con spazio", None])
def test_soprannomi_rifiutati(cattivo):
    with pytest.raises(regole.RegolaViolata):
        regole.soprannome_valido(cattivo)


def test_lo_stato_nel_pannello():
    assert regole.stato_pannello(None, False) == "nessuna"
    assert regole.stato_pannello(None, True) == "rinviato"
    assert regole.stato_pannello("in_attesa", True) == "in_attesa"
    assert regole.stato_pannello("da_rifare", False) == "da_rifare"
