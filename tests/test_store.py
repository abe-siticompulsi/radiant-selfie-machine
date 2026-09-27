import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from rsm.store import Iscrizione, Persona, Store

T0 = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)


def test_lo_schema_si_puo_creare_due_volte(store):
    store.crea_schema()


def test_persone_per_impronta_e_in_ordine(store):
    store.aggiungi_persona("gio", "master", "h-gio")
    store.aggiungi_persona("emi", "giocatore", "h-emi")
    assert store.persona_da_impronta("h-gio") == Persona("gio", "master")
    assert store.persona_da_impronta("sconosciuta") is None
    assert [p.soprannome for p in store.persone()] == ["emi", "gio"]


def test_una_persona_non_si_aggiunge_due_volte(store):
    store.aggiungi_persona("emi", "giocatore", "h1")
    with pytest.raises(sqlite3.IntegrityError):
        store.aggiungi_persona("emi", "giocatore", "h2")


def test_sostituire_il_gettone_annulla_il_vecchio(store):
    store.aggiungi_persona("emi", "giocatore", "vecchio")
    assert store.sostituisci_gettone("emi", "nuovo")
    assert store.persona_da_impronta("vecchio") is None
    assert store.persona_da_impronta("nuovo") == Persona("emi", "giocatore")
    assert not store.sostituisci_gettone("nessuno", "x")


def test_rimuovere_una_persona_toglie_anche_le_sue_iscrizioni(store):
    store.aggiungi_persona("prova", "giocatore", "h")
    store.aggiungi_iscrizione(Iscrizione("https://push/1", "prova", "p", "a"))
    assert store.rimuovi_persona("prova")
    assert store.persona_da_impronta("h") is None
    assert store.iscrizioni_di("prova") == []
    assert not store.rimuovi_persona("prova")


def test_un_ruolo_sconosciuto_e_rifiutato_dal_database(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.aggiungi_persona("x", "imperatore", "h")


def test_giri_crea_leggi_chiudi(store):
    assert store.ultimo_giro() is None
    g1 = store.crea_giro(T0, "gio")
    g2 = store.crea_giro(T0 + timedelta(days=3), "abe")
    assert store.ultimo_giro() == g2
    assert store.giro(g1.id) == g1
    assert store.giro(999) is None
    store.chiudi_giro(g1.id, T0 + timedelta(hours=1))
    store.chiudi_giro(g1.id, T0 + timedelta(hours=5))  # una chiusura non si sposta
    assert store.giro(g1.id).chiuso_alle == T0 + timedelta(hours=1)


def test_le_date_non_perdono_il_fuso_e_rifiutano_le_ingenue(store):
    g = store.crea_giro(T0, "gio")
    assert store.giro(g.id).aperto_alle.tzinfo is not None
    with pytest.raises(ValueError, match="fuso"):
        store.crea_giro(datetime(2026, 10, 4, 19, 30), "gio")


def test_giri_dal_comprende_il_limite(store):
    prima = store.crea_giro(T0 - timedelta(microseconds=1), "gio")
    esatto = store.crea_giro(T0, "gio")
    dopo = store.crea_giro(T0 + timedelta(hours=1), "gio")
    assert [g.id for g in store.giri_dal(T0)] == [esatto.id, dopo.id]
    assert prima.id not in [g.id for g in store.giri_dal(T0)]


def test_legare_un_giro_riesce_una_volta_sola(store):
    g = store.crea_giro(T0, "gio")
    assert store.lega(g.id, "2026-10-04")
    assert not store.lega(g.id, "2026-10-05")
    assert store.giro(g.id).sessione == "2026-10-04"


def test_salva_foto_crea_poi_sostituisce_e_azzera_motivo_e_messaggi(store):
    g = store.crea_giro(T0, "gio")
    prima = store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    assert prima.versione == 1 and prima.stato == "in_attesa"
    store.imposta_messaggio_bot(g.id, "emi", 1, 555)
    store.decidi(g.id, "emi", 1, "da_rifare", "sfocata")
    seconda = store.salva_foto(g.id, "emi", "in_attesa", "sha2", 20, T0 + timedelta(minutes=1))
    assert seconda.versione == 2
    assert (seconda.sha256, seconda.byte, seconda.motivo, seconda.messaggio_bot) == (
        "sha2",
        20,
        None,
        None,
    )


def test_una_foto_accettata_non_si_sostituisce(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "abe", "accettata", "sha1", 10, T0)
    assert store.salva_foto(g.id, "abe", "in_attesa", "sha2", 20, T0) is None
    assert store.foto(g.id, "abe").sha256 == "sha1"


def test_decidere_vale_solo_per_la_versione_vista_e_in_attesa(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    store.salva_foto(g.id, "emi", "in_attesa", "sha2", 10, T0)
    assert not store.decidi(g.id, "emi", 1, "accettata", None)
    assert store.decidi(g.id, "emi", 2, "accettata", None)
    assert not store.decidi(g.id, "emi", 2, "da_rifare", None)
    assert store.foto(g.id, "emi").stato == "accettata"


def test_l_attesa_del_motivo(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    assert store.imposta_attesa_motivo(g.id, "emi", 1, 777)
    assert store.foto_in_attesa_di_motivo(777).soprannome == "emi"
    assert store.foto_in_attesa_di_motivo(778) is None
    store.decidi(g.id, "emi", 1, "da_rifare", "occhi chiusi")
    assert store.foto_in_attesa_di_motivo(777) is None
    assert not store.imposta_attesa_motivo(g.id, "emi", 1, 779)


def test_una_foto_nuova_annulla_l_attesa_del_motivo(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    store.imposta_attesa_motivo(g.id, "emi", 1, 777)
    store.salva_foto(g.id, "emi", "in_attesa", "sha2", 10, T0)
    assert store.foto_in_attesa_di_motivo(777) is None


def test_foto_del_giro_giri_con_foto_e_cancellazione(store):
    g1 = store.crea_giro(T0, "gio")
    g2 = store.crea_giro(T0 + timedelta(days=3), "gio")
    store.salva_foto(g1.id, "sem", "in_attesa", "a", 1, T0)
    store.salva_foto(g1.id, "emi", "in_attesa", "b", 1, T0)
    assert [f.soprannome for f in store.foto_del_giro(g1.id)] == ["emi", "sem"]
    assert [g.id for g in store.giri_con_foto()] == [g1.id]
    store.cancella_foto_giro(g1.id)
    assert store.foto_del_giro(g1.id) == []
    assert store.giri_con_foto() == []
    assert store.giro(g2.id) is not None


def test_rinvii_scadenza_e_notifica(store):
    g = store.crea_giro(T0, "gio")
    store.imposta_rinvio(g.id, "emi", T0 + timedelta(minutes=10))
    assert store.rinvii_scaduti(T0 + timedelta(minutes=9)) == []
    scaduti = store.rinvii_scaduti(T0 + timedelta(minutes=10))
    assert [(r.soprannome, r.notificato) for r in scaduti] == [("emi", False)]
    store.segna_rinvio_notificato(g.id, "emi")
    assert store.rinvii_scaduti(T0 + timedelta(hours=1)) == []
    store.imposta_rinvio(g.id, "emi", T0 + timedelta(minutes=30))  # un nuovo «Salta»
    assert store.rinvio(g.id, "emi").notificato is False


def test_iscrizioni(store):
    store.aggiungi_iscrizione(Iscrizione("https://push/1", "emi", "p1", "a1"))
    store.aggiungi_iscrizione(Iscrizione("https://push/1", "sem", "p2", "a2"))
    assert store.iscrizioni_di("emi") == []
    assert store.iscrizioni_di("sem") == [Iscrizione("https://push/1", "sem", "p2", "a2")]
    store.togli_iscrizione("https://push/1", soprannome="emi")  # non è sua
    assert len(store.iscrizioni_di("sem")) == 1
    store.togli_iscrizione("https://push/1")
    assert store.iscrizioni_di("sem") == []


def test_valori(store):
    assert store.leggi_valore("offset") is None
    store.scrivi_valore("offset", "5")
    store.scrivi_valore("offset", "6")
    assert store.leggi_valore("offset") == "6"


def test_un_altro_store_sullo_stesso_file_vede_i_dati(store, tmp_path):
    store.aggiungi_persona("emi", "giocatore", "h")
    assert Store(tmp_path / "rsm.sqlite").persona_da_impronta("h") == Persona("emi", "giocatore")
