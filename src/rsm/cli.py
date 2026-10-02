"""`rsm`: le persone del servizio, il giro e la chiave del push, dalla riga di comando.

Si lancia dentro il container:

    docker compose exec rsm rsm persona aggiungi emi --ruolo giocatore

Il link personale si stampa una volta sola: il database ne tiene solo
l'impronta. Il gettone di `ctc` si stampa nudo, perché va nel portachiavi del
Mac e da nessun'altra parte.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from py_vapid import Vapid

from . import config, gettoni, regole
from .push import chiave_pubblica
from .store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rsm", description="Radiant Selfie Machine")
    comandi = parser.add_subparsers(dest="comando", required=True)

    persona = comandi.add_parser("persona", help="le persone del servizio")
    azioni = persona.add_subparsers(dest="azione", required=True)
    aggiungi = azioni.add_parser("aggiungi", help="aggiunge una persona e stampa il suo link")
    aggiungi.add_argument("soprannome")
    aggiungi.add_argument("--ruolo", choices=regole.RUOLI, required=True)
    revoca = azioni.add_parser("revoca", help="annulla il link, toglie le iscrizioni push e stampa un link nuovo")
    revoca.add_argument("soprannome")
    rimuovi = azioni.add_parser("rimuovi", help="toglie una persona e le sue iscrizioni push")
    rimuovi.add_argument("soprannome")
    azioni.add_parser("elenco", help="elenca le persone")

    giro = comandi.add_parser("giro", help="il giro dei selfie")
    azioni_giro = giro.add_subparsers(dest="azione", required=True)
    azioni_giro.add_parser("chiudi", help="chiude subito il giro aperto")

    vapid = comandi.add_parser("vapid", help="la chiave del push")
    azioni_vapid = vapid.add_subparsers(dest="azione", required=True)
    genera = azioni_vapid.add_parser("genera", help="genera la chiave privata VAPID")
    genera.add_argument("percorso", type=Path)
    return parser


def _consegna(ruolo: str, soprannome: str, gettone: str, env: Mapping[str, str]) -> str:
    if ruolo == regole.CTC:
        return f"gettone di ctc (va nel portachiavi del Mac, e da nessun'altra parte):\n{gettone}"
    return f"link di {soprannome} ({ruolo}), da consegnare in privato:\n{config.url_base(env)}/p/{gettone}/"


def _persona(args: argparse.Namespace, env: Mapping[str, str], stampa: Callable) -> int:
    store = Store(config.percorso_db(env))
    store.crea_schema()
    if args.azione == "elenco":
        persone = store.persone()
        stampa("\n".join(f"{p.soprannome}  {p.ruolo}" for p in persone) or "nessuna persona")
        return 0
    soprannome = regole.soprannome_valido(args.soprannome)
    if args.azione == "aggiungi":
        if args.ruolo != regole.CTC:
            config.url_base(env)  # prima di scrivere: senza base non c'è link da consegnare
        gettone = gettoni.genera()
        try:
            store.aggiungi_persona(soprannome, args.ruolo, gettoni.impronta(gettone))
        except sqlite3.IntegrityError:
            stampa(f"{soprannome} esiste già: per un link nuovo usa «rsm persona revoca {soprannome}»")
            return 1
        stampa(_consegna(args.ruolo, soprannome, gettone, env))
        return 0
    if args.azione == "revoca":
        esistente = next((p for p in store.persone() if p.soprannome == soprannome), None)
        if esistente is None:
            stampa(f"nessuna persona con il soprannome {soprannome}")
            return 1
        if esistente.ruolo != regole.CTC:
            config.url_base(env)
        gettone = gettoni.genera()
        store.sostituisci_gettone(soprannome, gettoni.impronta(gettone))
        # Le iscrizioni sono legate al soprannome, non al link: senza toglierle,
        # chi ha il link vecchio continuerebbe a ricevere i push.
        tolte = store.togli_iscrizioni_di(soprannome)
        if esistente.ruolo != regole.CTC:
            stampa(f"iscrizioni push tolte: {tolte}; le notifiche vanno riattivate dal link nuovo")
        stampa(_consegna(esistente.ruolo, soprannome, gettone, env))
        return 0
    if not store.rimuovi_persona(soprannome):
        stampa(f"nessuna persona con il soprannome {soprannome}")
        return 1
    stampa(f"{soprannome} rimosso, con le sue iscrizioni push")
    return 0


def _chi_e_quando(giro: regole.Giro) -> str:
    aperto = giro.aperto_alle.astimezone(UTC)
    return f"{giro.aperto_da} il {aperto:%Y-%m-%d} alle {aperto:%H:%M} UTC"


def _giro(env: Mapping[str, str], stampa: Callable, adesso: Callable[[], datetime]) -> int:
    """Chiude subito il giro aperto, per esempio quello della prova generale se la
    serata vera cade a meno di 12 ore: «Apri il giro» lo riuserebbe. Un giro già
    chiuso, o scaduto da solo dopo 48 ore, non si tocca. L'ora è in UTC, come nel
    servizio: è quella che il servizio ha registrato."""
    store = Store(config.percorso_db(env))
    store.crea_schema()
    ora = adesso()
    ultimo = store.ultimo_giro()
    if ultimo is None or not regole.aperto(ultimo, ora):
        stampa("nessun giro aperto: niente da chiudere")
        return 0
    if not store.chiudi_giro(ultimo.id, ora):
        # Il servizio è un altro processo: fra la lettura e la scrittura «Apri il
        # giro» può averlo chiuso, e aperto il giro della serata. Il comando non l'ha
        # chiuso, e non consiglia di rilanciarsi: chiuderebbe quello nuovo. Dice
        # com'è lo stato adesso, riletto. Il giro N è chiuso di sicuro (la scrittura
        # non ha trovato niente), anche se l'altro ha letto l'orologio un istante dopo
        # di noi; un giro più nuovo si giudica con l'ora di adesso, non con quella vecchia.
        gia_detto = f"il giro {ultimo.id} è stato chiuso nel frattempo da altri, non da questo comando."
        ora_aperto = store.ultimo_giro()
        if ora_aperto is not None and ora_aperto.id != ultimo.id and regole.aperto(ora_aperto, adesso()):
            stampa(
                f"{gia_detto} Adesso è aperto il giro {ora_aperto.id}, l'ha aperto {_chi_e_quando(ora_aperto)}: "
                "rilanciare il comando chiuderebbe questo."
            )
        else:
            stampa(f"{gia_detto} Adesso non c'è un giro aperto.")
        return 1
    stampa(f"giro {ultimo.id} chiuso: l'aveva aperto {_chi_e_quando(ultimo)}")
    return 0


def _vapid(args: argparse.Namespace, stampa: Callable) -> int:
    percorso: Path = args.percorso
    chiave = Vapid()
    chiave.generate_keys()
    try:
        descrittore = os.open(percorso, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        stampa(f"{percorso} esiste già: non sovrascrivo una chiave che le pagine stanno usando")
        return 1
    with os.fdopen(descrittore, "wb") as file:
        file.write(chiave.private_pem())
    stampa(f"chiave privata scritta in {percorso} (permessi 600). Chiave pubblica:\n{chiave_pubblica(chiave)}")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    stampa: Callable = print,
    adesso: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    env = os.environ if env is None else env
    args = _parser().parse_args(argv)
    try:
        if args.comando == "persona":
            return _persona(args, env, stampa)
        if args.comando == "giro":
            return _giro(env, stampa, adesso)
        return _vapid(args, stampa)
    except (config.ConfigurazioneErrata, regole.RegolaViolata) as e:
        stampa(f"errore: {e}")
        return 2
