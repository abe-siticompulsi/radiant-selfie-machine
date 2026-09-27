import base64
import os
import stat

from rsm import gettoni
from rsm.cli import main
from rsm.store import Store


def ambiente(tmp_path):
    return {"RSM_DB": str(tmp_path / "rsm.sqlite"), "RSM_URL_BASE": "https://selfie.example.org"}


def esegui(argomenti, env):
    righe = []
    codice = main(argomenti, env=env, stampa=righe.append)
    return codice, "\n".join(righe)


def gettone_dal_link(uscita):
    return uscita.strip().splitlines()[-1].removeprefix("https://selfie.example.org/p/").rstrip("/")


def test_aggiungere_stampa_il_link_una_volta(tmp_path):
    env = ambiente(tmp_path)
    codice, uscita = esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    assert codice == 0
    assert "https://selfie.example.org/p/" in uscita
    persona = Store(env["RSM_DB"]).persona_da_impronta(gettoni.impronta(gettone_dal_link(uscita)))
    assert (persona.soprannome, persona.ruolo) == ("emi", "giocatore")


def test_una_persona_non_si_aggiunge_due_volte(tmp_path):
    env = ambiente(tmp_path)
    esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    codice, uscita = esegui(["persona", "aggiungi", "emi", "--ruolo", "master"], env)
    assert codice == 1
    assert "esiste già" in uscita


def test_il_gettone_di_ctc_si_stampa_nudo(tmp_path):
    env = ambiente(tmp_path)
    codice, uscita = esegui(["persona", "aggiungi", "ctc", "--ruolo", "ctc"], env)
    assert codice == 0
    gettone = uscita.strip().splitlines()[-1]
    assert "http" not in gettone
    assert Store(env["RSM_DB"]).persona_da_impronta(gettoni.impronta(gettone)).ruolo == "ctc"


def test_revocare_cambia_il_link(tmp_path):
    env = ambiente(tmp_path)
    _, prima = esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    codice, dopo = esegui(["persona", "revoca", "emi"], env)
    assert codice == 0
    store = Store(env["RSM_DB"])
    assert store.persona_da_impronta(gettoni.impronta(gettone_dal_link(prima))) is None
    assert store.persona_da_impronta(gettoni.impronta(gettone_dal_link(dopo))).soprannome == "emi"
    assert esegui(["persona", "revoca", "nessuno"], env)[0] == 1


def test_rimuovere_ed_elencare(tmp_path):
    env = ambiente(tmp_path)
    esegui(["persona", "aggiungi", "gio", "--ruolo", "master"], env)
    esegui(["persona", "aggiungi", "prova", "--ruolo", "giocatore"], env)
    assert esegui(["persona", "rimuovi", "prova"], env)[0] == 0
    assert esegui(["persona", "rimuovi", "prova"], env)[0] == 1
    codice, uscita = esegui(["persona", "elenco"], env)
    assert codice == 0
    assert uscita == "gio  master"


def test_elenco_vuoto(tmp_path):
    assert esegui(["persona", "elenco"], ambiente(tmp_path)) == (0, "nessuna persona")


def test_errori_di_configurazione_e_di_argomenti(tmp_path):
    assert esegui(["persona", "aggiungi", "Emi!", "--ruolo", "giocatore"], ambiente(tmp_path))[0] == 2
    assert esegui(["persona", "elenco"], {})[0] == 2
    senza_base = {"RSM_DB": str(tmp_path / "rsm.sqlite")}
    codice, uscita = esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], senza_base)
    assert codice == 2 and "RSM_URL_BASE" in uscita
    assert Store(senza_base["RSM_DB"]).persone() == []  # niente persona senza link da consegnare


def test_vapid_genera_una_chiave_privata_leggibile_solo_dal_proprietario(tmp_path):
    percorso = tmp_path / "vapid.pem"
    codice, uscita = esegui(["vapid", "genera", str(percorso)], {})
    assert codice == 0
    assert stat.S_IMODE(os.stat(percorso).st_mode) == 0o600
    assert percorso.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    chiave = uscita.strip().splitlines()[-1]
    assert len(base64.urlsafe_b64decode(chiave + "=")) == 65


def test_vapid_non_sovrascrive(tmp_path):
    percorso = tmp_path / "vapid.pem"
    percorso.write_text("già qui")
    codice, uscita = esegui(["vapid", "genera", str(percorso)], {})
    assert codice == 1
    assert "non sovrascrivo" in uscita
    assert percorso.read_text() == "già qui"
