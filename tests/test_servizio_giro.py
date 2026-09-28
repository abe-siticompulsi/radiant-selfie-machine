from datetime import timedelta

import pytest

from rsm import foto
from rsm.servizio import (
    TESTO_INVITO_GRUPPO,
    TTL_INVITO,
    Conflitto,
    GiroChiuso,
    NonTrovato,
    Servizio,
)
from tests.finti import impostazioni_di_prova, telegram_guasto
from tests.immagini import jpeg, png


def chi(persone, soprannome):
    return persone[soprannome][0]


def apri(servizio, persone):
    return servizio.apri_giro(chi(persone, "gio"))["giro"]["id"]


def test_la_persona_si_riconosce_dal_gettone(servizio, persone):
    persona, gettone = persone["emi"]
    assert servizio.persona(gettone) == persona
    assert servizio.persona("inventato") is None
    assert servizio.persona("") is None


def test_un_giocatore_non_apre_il_giro(servizio, persone):
    with pytest.raises(NonTrovato):
        servizio.apri_giro(chi(persone, "emi"))


def test_il_master_apre_il_giro_e_il_bot_lo_annuncia_nel_gruppo_di_prova(servizio, persone, telegram, orologio):
    risposta = servizio.apri_giro(chi(persone, "gio"))
    assert risposta["nuovo"] is True
    assert risposta["annuncio"] == {"esito": "inviato", "gruppo": "prova"}
    assert risposta["giro"]["aperto_alle"] == orologio.adesso.isoformat()
    assert risposta["giro"]["scade_alle"] == (orologio.adesso + timedelta(hours=48)).isoformat()
    assert telegram.di_tipo("scrivi") == [{"chat_id": -100, "testo": TESTO_INVITO_GRUPPO}]


def test_con_la_sicura_armata_l_annuncio_va_al_party(store, telegram, notifiche, tmp_path, orologio, persone):
    imp = impostazioni_di_prova(tmp_path, gruppo_party=-987654321)
    armato = Servizio(
        store=store, cartella_foto=imp.cartella_foto, telegram=telegram,
        notifiche=notifiche, impostazioni=imp, chiave_vapid="k", ora=orologio,
    )
    assert armato.apri_giro(chi(persone, "abe"))["annuncio"] == {"esito": "inviato", "gruppo": "party"}
    assert telegram.di_tipo("scrivi")[0]["chat_id"] == -987654321


def test_riaprire_entro_12_ore_restituisce_lo_stesso_giro(servizio, persone, telegram, orologio):
    primo = servizio.apri_giro(chi(persone, "gio"))
    orologio.avanza(hours=11, minutes=59)
    secondo = servizio.apri_giro(chi(persone, "abe"))
    assert secondo == {"giro": primo["giro"], "nuovo": False, "annuncio": None}
    assert len(telegram.di_tipo("scrivi")) == 1


def test_dopo_12_ore_il_vecchio_si_chiude_e_se_ne_apre_uno_nuovo(servizio, persone, store, orologio):
    primo = servizio.apri_giro(chi(persone, "gio"))["giro"]
    orologio.avanza(hours=12)
    secondo = servizio.apri_giro(chi(persone, "gio"))["giro"]
    assert secondo["id"] != primo["id"]
    assert store.giro(primo["id"]).chiuso_alle == orologio.adesso


def test_se_telegram_non_risponde_il_giro_si_apre_e_lo_si_dice(servizio, persone, telegram, store):
    telegram.guasto = telegram_guasto()
    risposta = servizio.apri_giro(chi(persone, "gio"))
    assert risposta["nuovo"] is True
    assert risposta["annuncio"] == {"esito": "fallito", "gruppo": "prova"}
    assert store.ultimo_giro() is not None


def test_l_invito_push_va_a_chi_scatta_tranne_chi_ha_aperto(servizio, persone, notifiche):
    servizio.invita("gio")
    assert sorted(n["soprannome"] for n in notifiche.inviate) == ["abe", "emi", "sem"]
    assert all(n["ttl"] == TTL_INVITO for n in notifiche.inviate)


def test_la_foto_di_un_giocatore_arriva_in_attesa(servizio, persone, impostazioni):
    giro_id = apri(servizio, persone)
    dati = jpeg()
    ricevuta = servizio.ricevi_foto(chi(persone, "emi"), giro_id, dati)
    assert (ricevuta.foto.stato, ricevuta.foto.versione) == ("in_attesa", 1)
    assert ricevuta.foto.sha256 == foto.impronta(dati)
    assert ricevuta.messaggio_da_ritirare is None
    assert foto.leggi(impostazioni.cartella_foto, giro_id, "emi", 1) == dati


def test_la_foto_di_alberto_e_accettata_all_arrivo(servizio, persone):
    giro_id = apri(servizio, persone)
    assert servizio.ricevi_foto(chi(persone, "abe"), giro_id, jpeg()).foto.stato == "accettata"


def test_una_foto_nuova_sostituisce_la_vecchia_anche_su_disco(servizio, persone, impostazioni, store):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg(colore=(1, 2, 3)))
    store.imposta_messaggio_bot(giro_id, "emi", 1, 555)
    seconda = servizio.ricevi_foto(emi, giro_id, jpeg(colore=(9, 9, 9)))
    assert seconda.foto.versione == 2
    assert seconda.messaggio_da_ritirare == 555
    assert not foto.percorso(impostazioni.cartella_foto, giro_id, "emi", 1).exists()
    assert foto.percorso(impostazioni.cartella_foto, giro_id, "emi", 2).exists()


def test_se_il_file_non_si_promuove_la_foto_torna_come_prima(
    servizio, persone, impostazioni, store, monkeypatch
):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg())
    prima = store.foto(giro_id, "emi")

    def guasto(*args, **kwargs):
        raise OSError("disco pieno")

    monkeypatch.setattr(foto, "promuovi", guasto)
    with pytest.raises(OSError, match="disco pieno"):
        servizio.ricevi_foto(emi, giro_id, jpeg())
    assert store.foto(giro_id, "emi") == prima
    assert foto.percorso(impostazioni.cartella_foto, giro_id, "emi", 1).exists()
    cartella = impostazioni.cartella_foto / str(giro_id)
    assert sorted(f.name for f in cartella.iterdir()) == ["emi-1.jpg"]


def test_se_il_file_non_si_promuove_alla_prima_foto_non_resta_nulla(
    servizio, persone, impostazioni, store, monkeypatch
):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")

    def guasto(*args, **kwargs):
        raise OSError("disco pieno")

    monkeypatch.setattr(foto, "promuovi", guasto)
    with pytest.raises(OSError, match="disco pieno"):
        servizio.ricevi_foto(emi, giro_id, jpeg())
    assert store.foto(giro_id, "emi") is None
    cartella = impostazioni.cartella_foto / str(giro_id)
    assert list(cartella.iterdir()) == []


def test_un_ripristino_senza_effetto_lascia_traccia_nel_log(
    servizio, persone, store, orologio, monkeypatch, caplog
):
    """Mentre il file non arrivava su disco è arrivata una versione più recente:
    il ripristino giustamente non la tocca, e il log lo dice."""
    giro_id = apri(servizio, persone)

    def guasto_dopo_un_invio_piu_recente(*args, **kwargs):
        store.salva_foto(giro_id, "emi", "in_attesa", "piu-recente", 1, orologio())
        raise OSError("disco pieno")

    monkeypatch.setattr(foto, "promuovi", guasto_dopo_un_invio_piu_recente)
    with pytest.raises(OSError, match="disco pieno"):
        servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    assert store.foto(giro_id, "emi").sha256 == "piu-recente"
    [avviso] = [r for r in caplog.records if r.name == "rsm.servizio"]
    assert avviso.levelname == "WARNING"
    assert "emi" in avviso.getMessage() and "non ripristinata" in avviso.getMessage()


def test_una_foto_accettata_non_si_sostituisce_e_non_lascia_file(servizio, persone, impostazioni):
    giro_id = apri(servizio, persone)
    abe = chi(persone, "abe")
    servizio.ricevi_foto(abe, giro_id, jpeg())
    with pytest.raises(Conflitto, match="definitiva"):
        servizio.ricevi_foto(abe, giro_id, jpeg())
    assert sorted(f.name for f in (impostazioni.cartella_foto / str(giro_id)).iterdir()) == ["abe-1.jpg"]


def test_una_foto_non_valida_non_lascia_traccia(servizio, persone, store, impostazioni):
    giro_id = apri(servizio, persone)
    with pytest.raises(foto.FotoNonJpeg):
        servizio.ricevi_foto(chi(persone, "emi"), giro_id, png())
    assert store.foto(giro_id, "emi") is None
    assert not (impostazioni.cartella_foto / str(giro_id)).exists()


def test_giro_inesistente_o_chiuso(servizio, persone, orologio):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    with pytest.raises(NonTrovato):
        servizio.ricevi_foto(emi, 999, jpeg())
    orologio.avanza(hours=48)
    with pytest.raises(GiroChiuso):
        servizio.ricevi_foto(emi, giro_id, jpeg())


def test_ctc_non_scatta(servizio, persone):
    giro_id = apri(servizio, persone)
    with pytest.raises(NonTrovato):
        servizio.ricevi_foto(chi(persone, "ctc"), giro_id, jpeg())


def test_la_foto_da_validare_arriva_ad_alberto_con_i_pulsanti(servizio, persone, telegram, store):
    giro_id = apri(servizio, persone)  # l'annuncio nel gruppo prende l'id 101
    dati = jpeg()
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, dati)
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    [inviata] = telegram.di_tipo("manda_foto")
    assert inviata["chat_id"] == 123456789
    assert inviata["dati"] == dati
    assert inviata["didascalia"] == "Selfie di emi"
    assert inviata["pulsanti"][0] == [("✅ Va bene", f"v|{giro_id}|emi|1|ok")]
    assert store.foto(giro_id, "emi").messaggio_bot == 102


def test_un_annuncio_vecchio_non_parte(servizio, persone, telegram):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    assert telegram.di_tipo("manda_foto") == []


def test_il_messaggio_della_foto_sostituita_si_ritira(servizio, persone, telegram):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 1, None)  # id 102
    seconda = servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 2, seconda.messaggio_da_ritirare)
    [ritiro] = telegram.di_tipo("modifica_didascalia")
    assert ritiro["messaggio"] == 102
    assert ritiro["pulsanti"] is None
    assert ritiro["testo"] == "↩️ Selfie di emi: sostituita da una foto nuova"
    assert len(telegram.di_tipo("manda_foto")) == 2


def test_se_il_bot_non_raggiunge_alberto_la_foto_resta_in_attesa(servizio, persone, telegram, store):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    telegram.guasto = telegram_guasto()
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    foto_emi = store.foto(giro_id, "emi")
    assert (foto_emi.stato, foto_emi.messaggio_bot) == ("in_attesa", None)


def test_salta_rimanda_di_10_minuti(servizio, persone, orologio):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    fino_a = servizio.rinvia(emi, giro_id)
    assert fino_a == orologio.adesso + timedelta(minutes=10)
    assert servizio.stato(emi)["rinvio_fino_a"] == fino_a.isoformat()
    orologio.avanza(minutes=10)
    assert servizio.stato(emi)["rinvio_fino_a"] is None


def test_lo_stato_senza_giro(servizio, persone, orologio):
    assert servizio.stato(chi(persone, "emi")) == {
        "persona": "emi",
        "ruolo": "giocatore",
        "ora": orologio.adesso.isoformat(),
        "vapid": "CHIAVE-PUBBLICA",
        "giro": None,
        "foto": None,
        "rinvio_fino_a": None,
    }


def test_lo_stato_con_la_foto(servizio, persone):
    giro_id = apri(servizio, persone)
    dati = jpeg()
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, dati)
    stato = servizio.stato(emi)
    assert stato["giro"]["id"] == giro_id
    assert stato["foto"] == {"stato": "in_attesa", "sha256": foto.impronta(dati), "motivo": None}
    assert "pannello" not in stato


def test_il_pannello_di_master_e_admin(servizio, persone):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    servizio.ricevi_foto(chi(persone, "abe"), giro_id, jpeg())
    servizio.rinvia(chi(persone, "sem"), giro_id)
    pannello = servizio.stato(chi(persone, "gio"))["pannello"]
    assert pannello == [
        {"soprannome": "abe", "stato": "accettata"},
        {"soprannome": "emi", "stato": "in_attesa"},
        {"soprannome": "gio", "stato": "nessuna"},
        {"soprannome": "sem", "stato": "rinviato"},
    ]
    assert servizio.stato(chi(persone, "abe"))["pannello"] == pannello
