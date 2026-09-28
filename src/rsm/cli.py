"""`rsm`: le persone del servizio e la chiave del push, dalla riga di comando.

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
) -> int:
    env = os.environ if env is None else env
    args = _parser().parse_args(argv)
    try:
        if args.comando == "persona":
            return _persona(args, env, stampa)
        return _vapid(args, stampa)
    except (config.ConfigurazioneErrata, regole.RegolaViolata) as e:
        stampa(f"errore: {e}")
        return 2
