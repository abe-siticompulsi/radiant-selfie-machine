from datetime import timedelta

import pytest

from rsm import foto
from rsm.servizio import TESTO_INVITO_PUSH, Conflitto, NonTrovato, RichiestaErrata
from tests.immagini import jpeg


def chi(persone, soprannome):
    return persone[soprannome][0]


def apri(servizio, persone):
    return servizio.apri_giro(chi(persone, "gio"))["giro"]["id"]


def test_giri_dal_comprende_il_limite(servizio, persone, orologio):
    primo = apri(servizio, persone)
    orologio.avanza(hours=13)
    secondo = apri(servizio, persone)
    assert [g["id"] for g in servizio.giri_dal(orologio.adesso)] == [secondo]
    elenco = servizio.giri_dal(orologio.adesso - timedelta(hours=13))
    assert [(g["id"], g["aperto"]) for g in elenco] == [(primo, False), (secondo, True)]


def test_legare_e_idempotente_per_la_stessa_sessione(servizio, persone):
    giro_id = apri(servizio, persone)
    assert servizio.lega(giro_id, "2026-10-04")["sessione"] == "2026-10-04"
    assert servizio.lega(giro_id, "2026-10-04")["sessione"] == "2026-10-04"
    with pytest.raises(Conflitto, match="2026-10-04"):
        servizio.lega(giro_id, "2026-10-11")


@pytest.mark.parametrize("sessione", ["4 ottobre", "2026-13-40", ""])
def test_una_sessione_malformata(servizio, persone, sessione):
    giro_id = apri(servizio, persone)
    with pytest.raises(RichiestaErrata):
        servizio.lega(giro_id, sessione)


def test_legare_un_giro_inesistente(servizio):
    with pytest.raises(NonTrovato):
        servizio.lega(999, "2026-10-04")


def test_elenco_e_byte_delle_foto(servizio, persone):
    giro_id = apri(servizio, persone)
    dati_emi = jpeg(colore=(1, 1, 1))
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, dati_emi)
    servizio.ricevi_foto(chi(persone, "abe"), giro_id, jpeg())
    assert servizio.foto_del_giro(giro_id) == [
        {"soprannome": "abe", "versione": 1, "stato": "accettata", "sha256": foto.impronta(jpeg()), "motivo": None},
        {"soprannome": "emi", "versione": 1, "stato": "in_attesa", "sha256": foto.impronta(dati_emi), "motivo": None},
    ]
    assert servizio.dati_foto(giro_id, "emi") == dati_emi
    with pytest.raises(NonTrovato):
        servizio.dati_foto(giro_id, "sem")
    with pytest.raises(NonTrovato):
        servizio.foto_del_giro(999)


def test_se_il_file_e_sparito_lo_si_dice(servizio, persone, impostazioni):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    foto.cancella(impostazioni.cartella_foto, giro_id, "emi", 1)
    with pytest.raises(NonTrovato, match="non c'è più"):
        servizio.dati_foto(giro_id, "emi")


def test_le_persone_per_ctc_doctor(servizio, persone):
    assert servizio.persone() == [
        {"soprannome": "abe", "ruolo": "admin"},
        {"soprannome": "emi", "ruolo": "giocatore"},
        {"soprannome": "gio", "ruolo": "master"},
        {"soprannome": "sem", "ruolo": "giocatore"},
    ]


def test_iscrizione_e_disiscrizione_push(servizio, persone, store):
    emi, sem = chi(persone, "emi"), chi(persone, "sem")
    servizio.iscrivi(emi, {"endpoint": "https://push.example/1", "keys": {"p256dh": "p", "auth": "a"}})
    assert len(store.iscrizioni_di("emi")) == 1
    servizio.disiscrivi(sem, "https://push.example/1")  # non è sua
    assert len(store.iscrizioni_di("emi")) == 1
    servizio.disiscrivi(emi, "https://push.example/1")
    assert store.iscrizioni_di("emi") == []


@pytest.mark.parametrize(
    "dati",
    [
        {"endpoint": "http://push.example/1", "keys": {"p256dh": "p", "auth": "a"}},
        {"endpoint": "https://push.example/1", "keys": {"p256dh": "p"}},
        {"endpoint": "https://push.example/1"},
        {},
    ],
)
def test_iscrizioni_non_valide(servizio, persone, dati):
    with pytest.raises(RichiestaErrata):
        servizio.iscrivi(chi(persone, "emi"), dati)


def test_ctc_non_si_iscrive(servizio, persone):
    with pytest.raises(NonTrovato):
        servizio.iscrivi(chi(persone, "ctc"), {"endpoint": "https://x", "keys": {"p256dh": "p", "auth": "a"}})


def test_il_rinvio_scaduto_si_notifica_una_volta_e_solo_a_chi_non_ha_scattato(servizio, persone, orologio, notifiche):
    giro_id = apri(servizio, persone)
    servizio.rinvia(chi(persone, "emi"), giro_id)
    servizio.rinvia(chi(persone, "sem"), giro_id)
    servizio.ricevi_foto(chi(persone, "sem"), giro_id, jpeg())
    orologio.avanza(minutes=9)
    assert servizio.notifica_rinvii_scaduti() == 0
    orologio.avanza(minutes=1)
    assert servizio.notifica_rinvii_scaduti() == 1
    assert [(n["soprannome"], n["testo"]) for n in notifiche.inviate] == [("emi", TESTO_INVITO_PUSH)]
    assert servizio.notifica_rinvii_scaduti() == 0


def test_nessun_rinvio_notificato_a_giro_chiuso(servizio, persone, orologio, store, notifiche):
    giro_id = apri(servizio, persone)
    servizio.rinvia(chi(persone, "emi"), giro_id)
    orologio.avanza(hours=49)
    assert servizio.notifica_rinvii_scaduti() == 0
    assert notifiche.inviate == []
    assert store.rinvio(giro_id, "emi").notificato is True


def test_la_pulizia_trenta_giorni_dopo_la_fine_del_giro(servizio, persone, orologio, store, impostazioni):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    orologio.avanza(hours=48, days=30, seconds=-1)
    assert servizio.pulisci() == 0
    orologio.avanza(seconds=1)
    assert servizio.pulisci() == 1
    assert store.foto_del_giro(giro_id) == []
    assert not (impostazioni.cartella_foto / str(giro_id)).exists()
    assert store.giro(giro_id) is not None
    assert servizio.pulisci() == 0
