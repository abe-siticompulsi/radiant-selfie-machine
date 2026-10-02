"""Lo stato del servizio, in SQLite: persone, giri, foto, rinvii, iscrizioni.

Una connessione per operazione: FastAPI esegue le rotte sincrone in un pool di
thread, e una connessione condivisa fra thread è la via breve per un errore
che si vede solo sotto carico. Le date entrano ed escono come `datetime` con
fuso; nel database sono stringhe ISO in UTC a larghezza fissa, così il
confronto fra stringhe in SQL è anche un confronto fra istanti.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .regole import Giro

SCHEMA = """
CREATE TABLE IF NOT EXISTS persone (
    soprannome TEXT PRIMARY KEY,
    ruolo TEXT NOT NULL CHECK (ruolo IN ('giocatore', 'master', 'admin', 'ctc')),
    gettone TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS giri (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aperto_alle TEXT NOT NULL,
    aperto_da TEXT NOT NULL,
    chiuso_alle TEXT,
    sessione TEXT
);
CREATE TABLE IF NOT EXISTS foto (
    giro_id INTEGER NOT NULL REFERENCES giri (id),
    soprannome TEXT NOT NULL,
    versione INTEGER NOT NULL,
    stato TEXT NOT NULL CHECK (stato IN ('in_attesa', 'accettata', 'da_rifare')),
    sha256 TEXT NOT NULL,
    byte INTEGER NOT NULL,
    ricevuta_alle TEXT NOT NULL,
    motivo TEXT,
    messaggio_bot INTEGER,
    attesa_motivo INTEGER,
    PRIMARY KEY (giro_id, soprannome)
);
CREATE TABLE IF NOT EXISTS rinvii (
    giro_id INTEGER NOT NULL REFERENCES giri (id),
    soprannome TEXT NOT NULL,
    fino_a TEXT NOT NULL,
    notificato INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (giro_id, soprannome)
);
CREATE TABLE IF NOT EXISTS iscrizioni (
    endpoint TEXT PRIMARY KEY,
    soprannome TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valori (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Persona:
    soprannome: str
    ruolo: str


@dataclass(frozen=True)
class Foto:
    giro_id: int
    soprannome: str
    versione: int
    stato: str
    sha256: str
    byte: int
    ricevuta_alle: datetime
    motivo: str | None
    messaggio_bot: int | None
    attesa_motivo: int | None


@dataclass(frozen=True)
class Rinvio:
    giro_id: int
    soprannome: str
    fino_a: datetime
    notificato: bool


@dataclass(frozen=True)
class Iscrizione:
    endpoint: str
    soprannome: str
    p256dh: str
    auth: str


def _iso(momento: datetime) -> str:
    if momento.tzinfo is None:
        raise ValueError("data senza fuso orario")
    return momento.astimezone(UTC).isoformat(timespec="microseconds")


def _data(testo: str | None) -> datetime | None:
    return None if testo is None else datetime.fromisoformat(testo)


def _giro(riga: sqlite3.Row) -> Giro:
    return Giro(
        id=riga["id"],
        aperto_alle=datetime.fromisoformat(riga["aperto_alle"]),
        aperto_da=riga["aperto_da"],
        chiuso_alle=_data(riga["chiuso_alle"]),
        sessione=riga["sessione"],
    )


def _foto(riga: sqlite3.Row) -> Foto:
    return Foto(
        giro_id=riga["giro_id"],
        soprannome=riga["soprannome"],
        versione=riga["versione"],
        stato=riga["stato"],
        sha256=riga["sha256"],
        byte=riga["byte"],
        ricevuta_alle=datetime.fromisoformat(riga["ricevuta_alle"]),
        motivo=riga["motivo"],
        messaggio_bot=riga["messaggio_bot"],
        attesa_motivo=riga["attesa_motivo"],
    )


def _rinvio(riga: sqlite3.Row) -> Rinvio:
    return Rinvio(
        giro_id=riga["giro_id"],
        soprannome=riga["soprannome"],
        fino_a=datetime.fromisoformat(riga["fino_a"]),
        notificato=bool(riga["notificato"]),
    )


class Store:
    def __init__(self, percorso: Path | str) -> None:
        self._percorso = str(percorso)

    @contextmanager
    def _connessione(self) -> Iterator[sqlite3.Connection]:
        connessione = sqlite3.connect(self._percorso, timeout=10)
        connessione.row_factory = sqlite3.Row
        connessione.execute("PRAGMA foreign_keys = ON")
        try:
            with connessione:
                yield connessione
        finally:
            connessione.close()

    def crea_schema(self) -> None:
        with self._connessione() as c:
            c.execute("PRAGMA journal_mode = WAL")
            c.executescript(SCHEMA)

    # --- persone

    def aggiungi_persona(self, soprannome: str, ruolo: str, impronta: str) -> None:
        with self._connessione() as c:
            c.execute(
                "INSERT INTO persone (soprannome, ruolo, gettone) VALUES (?, ?, ?)",
                (soprannome, ruolo, impronta),
            )

    def sostituisci_gettone(self, soprannome: str, impronta: str) -> bool:
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE persone SET gettone = ? WHERE soprannome = ?", (impronta, soprannome)
            )
            return cursore.rowcount == 1

    def rimuovi_persona(self, soprannome: str) -> bool:
        with self._connessione() as c:
            c.execute("DELETE FROM iscrizioni WHERE soprannome = ?", (soprannome,))
            cursore = c.execute("DELETE FROM persone WHERE soprannome = ?", (soprannome,))
            return cursore.rowcount == 1

    def persona_da_impronta(self, impronta: str) -> Persona | None:
        with self._connessione() as c:
            riga = c.execute(
                "SELECT soprannome, ruolo FROM persone WHERE gettone = ?", (impronta,)
            ).fetchone()
        return None if riga is None else Persona(riga["soprannome"], riga["ruolo"])

    def persone(self) -> list[Persona]:
        with self._connessione() as c:
            righe = c.execute("SELECT soprannome, ruolo FROM persone ORDER BY soprannome").fetchall()
        return [Persona(r["soprannome"], r["ruolo"]) for r in righe]

    # --- giri

    def ultimo_giro(self) -> Giro | None:
        with self._connessione() as c:
            riga = c.execute("SELECT * FROM giri ORDER BY id DESC LIMIT 1").fetchone()
        return None if riga is None else _giro(riga)

    def giro(self, giro_id: int) -> Giro | None:
        with self._connessione() as c:
            riga = c.execute("SELECT * FROM giri WHERE id = ?", (giro_id,)).fetchone()
        return None if riga is None else _giro(riga)

    def crea_giro(self, aperto_alle: datetime, aperto_da: str) -> Giro:
        momento = _iso(aperto_alle)
        with self._connessione() as c:
            cursore = c.execute(
                "INSERT INTO giri (aperto_alle, aperto_da) VALUES (?, ?)", (momento, aperto_da)
            )
            giro_id = cursore.lastrowid
        return Giro(id=giro_id, aperto_alle=datetime.fromisoformat(momento), aperto_da=aperto_da)

    def chiudi_giro(self, giro_id: int, alle: datetime) -> bool:
        """Vero se l'ha chiuso questa chiamata; falso se era già chiuso (una
        chiusura non si sposta)."""
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE giri SET chiuso_alle = ? WHERE id = ? AND chiuso_alle IS NULL",
                (_iso(alle), giro_id),
            )
        return cursore.rowcount == 1

    def giri_dal(self, dal: datetime) -> list[Giro]:
        with self._connessione() as c:
            righe = c.execute(
                "SELECT * FROM giri WHERE aperto_alle >= ? ORDER BY id", (_iso(dal),)
            ).fetchall()
        return [_giro(r) for r in righe]

    def lega(self, giro_id: int, sessione: str) -> bool:
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE giri SET sessione = ? WHERE id = ? AND sessione IS NULL",
                (sessione, giro_id),
            )
            return cursore.rowcount == 1

    def giri_con_foto(self) -> list[Giro]:
        with self._connessione() as c:
            righe = c.execute(
                "SELECT DISTINCT g.* FROM giri g JOIN foto f ON f.giro_id = g.id ORDER BY g.id"
            ).fetchall()
        return [_giro(r) for r in righe]

    # --- foto

    def foto(self, giro_id: int, soprannome: str) -> Foto | None:
        with self._connessione() as c:
            riga = c.execute(
                "SELECT * FROM foto WHERE giro_id = ? AND soprannome = ?", (giro_id, soprannome)
            ).fetchone()
        return None if riga is None else _foto(riga)

    def foto_del_giro(self, giro_id: int) -> list[Foto]:
        with self._connessione() as c:
            righe = c.execute(
                "SELECT * FROM foto WHERE giro_id = ? ORDER BY soprannome", (giro_id,)
            ).fetchall()
        return [_foto(r) for r in righe]

    def salva_foto(
        self, giro_id: int, soprannome: str, stato: str, sha256: str, byte: int, alle: datetime
    ) -> Foto | None:
        """Crea o sostituisce la foto corrente di una persona in un giro.

        Restituisce `None` se la foto esistente è già accettata: la guardia sta
        nel SQL perché una decisione può arrivare fra il controllo e la
        scrittura.
        """
        with self._connessione() as c:
            cursore = c.execute(
                """
                INSERT INTO foto (giro_id, soprannome, versione, stato, sha256, byte, ricevuta_alle)
                VALUES (?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT (giro_id, soprannome) DO UPDATE SET
                    versione = foto.versione + 1,
                    stato = excluded.stato,
                    sha256 = excluded.sha256,
                    byte = excluded.byte,
                    ricevuta_alle = excluded.ricevuta_alle,
                    motivo = NULL,
                    messaggio_bot = NULL,
                    attesa_motivo = NULL
                WHERE foto.stato != 'accettata'
                """,
                (giro_id, soprannome, stato, sha256, byte, _iso(alle)),
            )
            if cursore.rowcount == 0:
                return None
            riga = c.execute(
                "SELECT * FROM foto WHERE giro_id = ? AND soprannome = ?", (giro_id, soprannome)
            ).fetchone()
        return _foto(riga)

    def ripristina_foto(
        self, giro_id: int, soprannome: str, versione: int, precedente: Foto | None
    ) -> bool:
        """Rimette la foto com'era prima di `salva_foto`, quando poi il file non
        è arrivato su disco: la riga non deve mai sopravvivere a una foto che
        non esiste. Guardata sulla versione fallita, così un caricamento più
        recente nel frattempo non viene toccato.
        """
        with self._connessione() as c:
            if precedente is None:
                cursore = c.execute(
                    "DELETE FROM foto WHERE giro_id = ? AND soprannome = ? AND versione = ?",
                    (giro_id, soprannome, versione),
                )
            else:
                cursore = c.execute(
                    """
                    UPDATE foto SET
                        versione = ?, stato = ?, sha256 = ?, byte = ?, ricevuta_alle = ?,
                        motivo = ?, messaggio_bot = ?, attesa_motivo = ?
                    WHERE giro_id = ? AND soprannome = ? AND versione = ?
                    """,
                    (
                        precedente.versione,
                        precedente.stato,
                        precedente.sha256,
                        precedente.byte,
                        _iso(precedente.ricevuta_alle),
                        precedente.motivo,
                        precedente.messaggio_bot,
                        precedente.attesa_motivo,
                        giro_id,
                        soprannome,
                        versione,
                    ),
                )
            return cursore.rowcount == 1

    def imposta_messaggio_bot(
        self, giro_id: int, soprannome: str, versione: int, messaggio: int
    ) -> bool:
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE foto SET messaggio_bot = ? "
                "WHERE giro_id = ? AND soprannome = ? AND versione = ?",
                (messaggio, giro_id, soprannome, versione),
            )
            return cursore.rowcount == 1

    def decidi(
        self, giro_id: int, soprannome: str, versione: int, stato: str, motivo: str | None
    ) -> bool:
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE foto SET stato = ?, motivo = ?, attesa_motivo = NULL "
                "WHERE giro_id = ? AND soprannome = ? AND versione = ? AND stato = 'in_attesa'",
                (stato, motivo, giro_id, soprannome, versione),
            )
            return cursore.rowcount == 1

    def imposta_attesa_motivo(
        self, giro_id: int, soprannome: str, versione: int, messaggio: int
    ) -> bool:
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE foto SET attesa_motivo = ? "
                "WHERE giro_id = ? AND soprannome = ? AND versione = ? AND stato = 'in_attesa'",
                (messaggio, giro_id, soprannome, versione),
            )
            return cursore.rowcount == 1

    def foto_in_attesa_di_motivo(self, messaggio: int) -> Foto | None:
        with self._connessione() as c:
            riga = c.execute(
                "SELECT * FROM foto WHERE attesa_motivo = ? AND stato = 'in_attesa'", (messaggio,)
            ).fetchone()
        return None if riga is None else _foto(riga)

    def cancella_foto_giro(self, giro_id: int) -> None:
        with self._connessione() as c:
            c.execute("DELETE FROM foto WHERE giro_id = ?", (giro_id,))

    # --- rinvii

    def imposta_rinvio(self, giro_id: int, soprannome: str, fino_a: datetime) -> None:
        with self._connessione() as c:
            c.execute(
                """
                INSERT INTO rinvii (giro_id, soprannome, fino_a, notificato) VALUES (?, ?, ?, 0)
                ON CONFLICT (giro_id, soprannome) DO UPDATE SET
                    fino_a = excluded.fino_a, notificato = 0
                """,
                (giro_id, soprannome, _iso(fino_a)),
            )

    def rinvio(self, giro_id: int, soprannome: str) -> Rinvio | None:
        with self._connessione() as c:
            riga = c.execute(
                "SELECT * FROM rinvii WHERE giro_id = ? AND soprannome = ?", (giro_id, soprannome)
            ).fetchone()
        return None if riga is None else _rinvio(riga)

    def rinvii_scaduti(self, ora: datetime) -> list[Rinvio]:
        with self._connessione() as c:
            righe = c.execute(
                "SELECT * FROM rinvii WHERE notificato = 0 AND fino_a <= ? "
                "ORDER BY giro_id, soprannome",
                (_iso(ora),),
            ).fetchall()
        return [_rinvio(r) for r in righe]

    def segna_rinvio_notificato(self, giro_id: int, soprannome: str, fino_a: datetime) -> bool:
        """Guardato sulla scadenza vista: un nuovo «Salta» arrivato mentre partiva
        il push del vecchio resta da notificare."""
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE rinvii SET notificato = 1 WHERE giro_id = ? AND soprannome = ? AND fino_a = ?",
                (giro_id, soprannome, _iso(fino_a)),
            )
            return cursore.rowcount == 1

    # --- iscrizioni push

    def aggiungi_iscrizione(self, iscrizione: Iscrizione) -> None:
        with self._connessione() as c:
            c.execute(
                """
                INSERT INTO iscrizioni (endpoint, soprannome, p256dh, auth) VALUES (?, ?, ?, ?)
                ON CONFLICT (endpoint) DO UPDATE SET
                    soprannome = excluded.soprannome,
                    p256dh = excluded.p256dh,
                    auth = excluded.auth
                """,
                (iscrizione.endpoint, iscrizione.soprannome, iscrizione.p256dh, iscrizione.auth),
            )

    def togli_iscrizione(self, endpoint: str, soprannome: str | None = None) -> None:
        with self._connessione() as c:
            if soprannome is None:
                c.execute("DELETE FROM iscrizioni WHERE endpoint = ?", (endpoint,))
            else:
                c.execute(
                    "DELETE FROM iscrizioni WHERE endpoint = ? AND soprannome = ?",
                    (endpoint, soprannome),
                )

    def togli_iscrizioni_di(self, soprannome: str) -> int:
        """Tutte le iscrizioni di una persona, per esempio quando il suo link è
        revocato: chi ha il link vecchio non deve più ricevere i suoi push."""
        with self._connessione() as c:
            return c.execute("DELETE FROM iscrizioni WHERE soprannome = ?", (soprannome,)).rowcount

    def iscrizioni_di(self, soprannome: str) -> list[Iscrizione]:
        with self._connessione() as c:
            righe = c.execute(
                "SELECT * FROM iscrizioni WHERE soprannome = ? ORDER BY endpoint", (soprannome,)
            ).fetchall()
        return [Iscrizione(r["endpoint"], r["soprannome"], r["p256dh"], r["auth"]) for r in righe]

    # --- valori

    def leggi_valore(self, chiave: str) -> str | None:
        with self._connessione() as c:
            riga = c.execute("SELECT valore FROM valori WHERE chiave = ?", (chiave,)).fetchone()
        return None if riga is None else riga["valore"]

    def scrivi_valore(self, chiave: str, valore: str) -> None:
        with self._connessione() as c:
            c.execute(
                "INSERT INTO valori (chiave, valore) VALUES (?, ?) "
                "ON CONFLICT (chiave) DO UPDATE SET valore = excluded.valore",
                (chiave, valore),
            )
