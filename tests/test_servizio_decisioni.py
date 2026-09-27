import pytest

from rsm import pulsanti, regole
from rsm.config import MOTIVI_PREDEFINITI
from rsm.servizio import TESTO_ACCETTATA, TITOLO, TTL_ESITO, Conflitto, NonTrovato, RichiestaErrata
from tests.finti import telegram_guasto
from tests.immagini import jpeg

TAGLIATA = "tagliata (controlla che tutta la testa sia ben visibile nella foto)"


def chi(persone, soprannome):
    return persone[soprannome][0]


def foto_in_attesa(servizio, persone):
    """Un giro aperto da gio (annuncio: id 101) e la foto di emi annunciata ad Alberto (id 102)."""
    giro_id = servizio.apri_giro(chi(persone, "gio"))["giro"]["id"]
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    return giro_id


def test_accettare(servizio, persone, store):
    giro_id = foto_in_attesa(servizio, persone)
    decisa = servizio.decidi(giro_id, "emi", 1, "accettata", None)
    assert decisa.stato == "accettata"
    assert store.foto(giro_id, "emi").stato == "accettata"


def test_chiedere_un_altra_foto_con_il_motivo_ripulito(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    decisa = servizio.decidi(giro_id, "emi", 1, "da_rifare", "  troppo buia ")
    assert (decisa.stato, decisa.motivo) == ("da_rifare", "troppo buia")


def test_la_versione_deve_essere_quella_vista(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    with pytest.raises(Conflitto, match="sostituita"):
        servizio.decidi(giro_id, "emi", 1, "accettata", None)


def test_una_foto_gia_decisa_non_si_decide_di_nuovo(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.decidi(giro_id, "emi", 1, "accettata", None)
    with pytest.raises(Conflitto, match="già stata decisa"):
        servizio.decidi(giro_id, "emi", 1, "da_rifare", None)


def test_richieste_sbagliate(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    with pytest.raises(RichiestaErrata):
        servizio.decidi(giro_id, "emi", 1, "accettata", "sfocata")
    with pytest.raises(RichiestaErrata, match="al massimo 200"):
        servizio.decidi(giro_id, "emi", 1, "da_rifare", "x" * 201)
    with pytest.raises(RichiestaErrata, match="sconosciuto"):
        servizio.decidi(giro_id, "emi", 1, "forse", None)
    with pytest.raises(NonTrovato):
        servizio.decidi(giro_id, "sem", 1, "accettata", None)


def test_dopo_l_accettazione_il_push_e_il_messaggio_aggiornato(servizio, persone, notifiche, telegram):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.dopo_decisione(servizio.decidi(giro_id, "emi", 1, "accettata", None))
    assert notifiche.inviate[-1] == {
        "soprannome": "emi", "titolo": TITOLO, "testo": TESTO_ACCETTATA, "ttl": TTL_ESITO,
    }
    [modifica] = telegram.di_tipo("modifica_didascalia")
    assert modifica["messaggio"] == 102
    assert modifica["testo"] == "✅ Selfie di emi: accettata"
    assert modifica["pulsanti"] is None


def test_dopo_la_richiesta_il_push_porta_il_motivo(servizio, persone, notifiche, telegram):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.dopo_decisione(servizio.decidi(giro_id, "emi", 1, "da_rifare", TAGLIATA))
    assert notifiche.inviate[-1]["testo"] == f"Alberto chiede un'altra foto: {TAGLIATA}"
    assert telegram.di_tipo("modifica_didascalia")[-1]["testo"] == (
        f"🔄 Selfie di emi: chiesta un'altra foto — {TAGLIATA}"
    )


def test_dopo_la_richiesta_senza_motivo(servizio, persone, notifiche, telegram):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.dopo_decisione(servizio.decidi(giro_id, "emi", 1, "da_rifare", None))
    assert notifiche.inviate[-1]["testo"] == "Alberto chiede un'altra foto"
    assert telegram.di_tipo("modifica_didascalia")[-1]["testo"] == "🔄 Selfie di emi: chiesta un'altra foto"


def test_la_pagina_vede_il_motivo(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.decidi(giro_id, "emi", 1, "da_rifare", "troppo buia")
    stato = servizio.stato(chi(persone, "emi"))
    assert (stato["foto"]["stato"], stato["foto"]["motivo"]) == ("da_rifare", "troppo buia")


def test_se_telegram_non_risponde_la_decisione_resta(servizio, persone, telegram, store, notifiche):
    giro_id = foto_in_attesa(servizio, persone)
    decisa = servizio.decidi(giro_id, "emi", 1, "accettata", None)
    telegram.guasto = telegram_guasto()
    servizio.dopo_decisione(decisa)
    assert store.foto(giro_id, "emi").stato == "accettata"
    assert notifiche.inviate[-1]["testo"] == TESTO_ACCETTATA


def test_altro_motivo_chiede_il_testo_e_lascia_i_pulsanti(servizio, persone, telegram, store):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    [domanda] = telegram.di_tipo("chiedi_risposta")
    assert domanda["chat_id"] == 123456789
    assert domanda["testo"].startswith(f"{pulsanti.DOMANDA_MOTIVO} emi")
    assert store.foto(giro_id, "emi").attesa_motivo == 103
    [modifica] = telegram.di_tipo("modifica_didascalia")
    assert modifica["testo"] == "✏️ Selfie di emi: aspetto il motivo…"
    assert modifica["pulsanti"] == pulsanti.tastiera(giro_id, "emi", 1, MOTIVI_PREDEFINITI)
    assert store.foto(giro_id, "emi").stato == "in_attesa"


def test_il_motivo_scritto_decide(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    decisa = servizio.motivo_scritto(103, "  hai gli occhi chiusi ")
    assert (decisa.stato, decisa.motivo) == ("da_rifare", "hai gli occhi chiusi")


def test_un_motivo_vuoto_o_troppo_lungo_non_decide(servizio, persone, store):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    with pytest.raises(regole.RegolaViolata, match="al massimo 200"):
        servizio.motivo_scritto(103, "x" * 201)
    with pytest.raises(regole.RegolaViolata, match="vuoto"):
        servizio.motivo_scritto(103, None)
    foto_emi = store.foto(giro_id, "emi")
    assert (foto_emi.stato, foto_emi.attesa_motivo) == ("in_attesa", 103)


def test_una_risposta_a_una_domanda_superata(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())  # la foto nuova annulla la domanda
    assert servizio.motivo_scritto(103, "sfocata") is None
    assert servizio.motivo_scritto(999, "sfocata") is None


def test_altro_motivo_su_una_foto_decisa_o_sostituita(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.decidi(giro_id, "emi", 1, "accettata", None)
    with pytest.raises(Conflitto, match="già stata decisa"):
        servizio.aspetta_motivo(giro_id, "emi", 1)
    sem = chi(persone, "sem")
    servizio.ricevi_foto(sem, giro_id, jpeg())
    servizio.ricevi_foto(sem, giro_id, jpeg())
    with pytest.raises(Conflitto, match="sostituita"):
        servizio.aspetta_motivo(giro_id, "sem", 1)
    with pytest.raises(NonTrovato):
        servizio.aspetta_motivo(giro_id, "nessuno", 1)
