import base64
import os
import stat
from datetime import UTC, datetime, timedelta

import pytest

from rsm import gettoni, regole
from rsm.cli import main
from rsm.store import Iscrizione, Store


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


def test_revocare_toglie_le_iscrizioni_push(tmp_path):
    env = ambiente(tmp_path)
    esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    store = Store(env["RSM_DB"])
    store.aggiungi_iscrizione(Iscrizione("https://push.example/1", "emi", "p", "a"))
    store.aggiungi_iscrizione(Iscrizione("https://push.example/2", "emi", "p", "a"))
    codice, uscita = esegui(["persona", "revoca", "emi"], env)
    assert codice == 0
    assert store.iscrizioni_di("emi") == []
    assert "iscrizioni push tolte: 2; le notifiche vanno riattivate dal link nuovo" in uscita


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


ADESSO = datetime(2026, 10, 3, 20, 30, tzinfo=UTC)


def chiudi(env):
    righe = []
    codice = main(["giro", "chiudi"], env=env, stampa=righe.append, adesso=lambda: ADESSO)
    return codice, "\n".join(righe)


def test_chiudere_il_giro_aperto_dice_quale_e_lo_chiude_adesso(tmp_path):
    env = ambiente(tmp_path)
    store = Store(env["RSM_DB"])
    store.crea_schema()
    giro = store.crea_giro(datetime(2026, 10, 3, 18, 5, tzinfo=UTC), "gio")
    codice, uscita = chiudi(env)
    assert codice == 0
    assert uscita == f"giro {giro.id} chiuso: l'aveva aperto gio il 2026-10-03 alle 18:05 UTC"
    chiuso = store.ultimo_giro()
    assert chiuso.chiuso_alle == ADESSO
    assert not regole.aperto(chiuso, ADESSO)


def test_senza_giri_non_c_e_niente_da_chiudere(tmp_path):
    codice, uscita = chiudi(ambiente(tmp_path))
    assert (codice, uscita) == (0, "nessun giro aperto: niente da chiudere")


def test_un_giro_scaduto_da_solo_non_si_tocca(tmp_path):
    env = ambiente(tmp_path)
    store = Store(env["RSM_DB"])
    store.crea_schema()
    store.crea_giro(ADESSO - regole.DURATA_GIRO - timedelta(minutes=1), "gio")
    assert chiudi(env) == (0, "nessun giro aperto: niente da chiudere")
    assert store.ultimo_giro().chiuso_alle is None  # la fine si calcola: niente da scrivere


def test_alle_48_ore_esatte_il_giro_e_gia_scaduto(tmp_path):
    env = ambiente(tmp_path)
    store = Store(env["RSM_DB"])
    store.crea_schema()
    store.crea_giro(ADESSO - regole.DURATA_GIRO, "gio")
    assert chiudi(env) == (0, "nessun giro aperto: niente da chiudere")
    assert store.ultimo_giro().chiuso_alle is None


def test_un_giro_gia_chiuso_non_si_tocca(tmp_path):
    env = ambiente(tmp_path)
    store = Store(env["RSM_DB"])
    store.crea_schema()
    giro = store.crea_giro(ADESSO - timedelta(hours=2), "abe")
    store.chiudi_giro(giro.id, ADESSO - timedelta(hours=1))
    assert chiudi(env) == (0, "nessun giro aperto: niente da chiudere")
    assert store.ultimo_giro().chiuso_alle == ADESSO - timedelta(hours=1)


@pytest.mark.parametrize("riapre", [True, False])
@pytest.mark.parametrize("scarto", [timedelta(seconds=-1), timedelta(seconds=1)])
def test_se_il_servizio_lo_chiude_nel_frattempo_il_comando_non_dice_di_averlo_chiuso(
    tmp_path, monkeypatch, riapre, scarto
):
    """Fra la lettura e la scrittura del comando, un altro processo chiude il giro:
    il servizio con «Apri il giro», che ne apre uno nuovo, o un secondo comando. Il
    comando non ha chiuso niente: non dice «chiuso», e dice com'è lo stato adesso,
    senza consigliare di rilanciarsi (chiuderebbe il giro nuovo, quello della serata).
    L'altro può aver letto l'orologio un istante prima o dopo il comando (`scarto`):
    in nessuno dei due casi il giro appena chiuso risulta aperto."""
    env = ambiente(tmp_path)
    store = Store(env["RSM_DB"])
    store.crea_schema()
    vecchio = store.crea_giro(ADESSO - timedelta(hours=20), "gio")
    originale = Store.chiudi_giro

    def chiuso_prima_da_altri(self, giro_id, alle):
        originale(self, giro_id, alle + scarto)
        if riapre:
            Store.crea_giro(self, datetime(2026, 10, 3, 20, 29, tzinfo=UTC), "gio")
        monkeypatch.setattr(Store, "chiudi_giro", originale)
        return originale(self, giro_id, alle)  # la scrittura del comando, che non trova niente

    monkeypatch.setattr(Store, "chiudi_giro", chiuso_prima_da_altri)
    codice, uscita = chiudi(env)
    assert codice == 1
    gia_detto = f"il giro {vecchio.id} è stato chiuso nel frattempo da altri, non da questo comando."
    if riapre:
        nuovo = store.ultimo_giro()
        assert uscita == (
            f"{gia_detto} Adesso è aperto il giro {nuovo.id}, l'ha aperto gio il 2026-10-03 alle 20:29 UTC: "
            "rilanciare il comando chiuderebbe questo."
        )
        assert regole.aperto(nuovo, ADESSO)  # il giro della serata resta aperto
    else:
        assert uscita == f"{gia_detto} Adesso non c'è un giro aperto."
    assert store.giro(vecchio.id).chiuso_alle == ADESSO + scarto  # la chiusura degli altri non si sposta
