import sqlite3
import threading

from rsm import cicli
from rsm.telegram import TelegramError
from tests.finti import TelegramFinto


class TelegramACicli(TelegramFinto):
    """Dà un lotto di aggiornamenti per chiamata; finiti i lotti, ferma il ciclo."""

    def __init__(self, fermo, lotti):
        super().__init__()
        self._fermo = fermo
        self._lotti = list(lotti)

    def aggiornamenti(self, offset, attesa):
        self.chiamate.append(("aggiornamenti", {"offset": offset, "attesa": attesa}))
        if not self._lotti:
            self._fermo.set()
            return []
        lotto = self._lotti.pop(0)
        if isinstance(lotto, Exception):
            raise lotto
        return lotto


class ValidatoreFinto:
    def __init__(self, esplodi_su=()):
        self.visti = []
        self._esplodi_su = set(esplodi_su)

    def gestisci(self, aggiornamento):
        self.visti.append(aggiornamento["update_id"])
        if aggiornamento["update_id"] in self._esplodi_su:
            raise RuntimeError("boom")


def offset_chiesti(telegram):
    return [a["offset"] for nome, a in telegram.chiamate if nome == "aggiornamenti"]


def test_gestisce_tutto_e_salva_l_offset(store):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [[{"update_id": 5}, {"update_id": 6}], [{"update_id": 7}]])
    validatore = ValidatoreFinto()
    cicli.ciclo_bot(telegram, validatore, store, fermo, attesa=0, pausa_errore=0)
    assert validatore.visti == [5, 6, 7]
    assert store.leggi_valore(cicli.CHIAVE_OFFSET) == "8"
    assert offset_chiesti(telegram) == [None, 7, 8]


def test_riparte_dall_offset_salvato(store):
    store.scrivi_valore(cicli.CHIAVE_OFFSET, "42")
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [])
    cicli.ciclo_bot(telegram, ValidatoreFinto(), store, fermo, attesa=0, pausa_errore=0)
    assert offset_chiesti(telegram) == [42]


def test_un_aggiornamento_che_esplode_non_ferma_il_ciclo(store):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [[{"update_id": 5}, {"update_id": 6}]])
    validatore = ValidatoreFinto(esplodi_su={5})
    cicli.ciclo_bot(telegram, validatore, store, fermo, attesa=0, pausa_errore=0)
    assert validatore.visti == [5, 6]
    assert store.leggi_valore(cicli.CHIAVE_OFFSET) == "7"


def test_un_errore_di_telegram_fa_riprovare(store):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [TelegramError("getUpdates: errore di rete"), [{"update_id": 1}]])
    validatore = ValidatoreFinto()
    cicli.ciclo_bot(telegram, validatore, store, fermo, attesa=0, pausa_errore=0)
    assert validatore.visti == [1]


class StoreCheSiBloccaUnaVolta:
    """Il primo `scrivi_valore` fallisce come SQLite sotto una scrittura concorrente."""

    def __init__(self, store):
        self._store = store
        self.fallito = False

    def leggi_valore(self, chiave):
        return self._store.leggi_valore(chiave)

    def scrivi_valore(self, chiave, valore):
        if not self.fallito:
            self.fallito = True
            raise sqlite3.OperationalError("database is locked")
        self._store.scrivi_valore(chiave, valore)


def test_un_errore_qualsiasi_non_uccide_il_ciclo(store):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [[{"update_id": 5}], [{"update_id": 6}]])
    validatore = ValidatoreFinto()
    bloccato = StoreCheSiBloccaUnaVolta(store)
    cicli.ciclo_bot(telegram, validatore, bloccato, fermo, attesa=0, pausa_errore=0)
    assert bloccato.fallito
    assert validatore.visti == [5, 6]
    assert store.leggi_valore(cicli.CHIAVE_OFFSET) == "7"
    assert offset_chiesti(telegram) == [None, 6, 7]


class ServizioFinto:
    def __init__(self, fermo=None, esplodi=False):
        self.chiamate = []
        self._fermo = fermo
        self._esplodi = esplodi

    def notifica_rinvii_scaduti(self):
        self.chiamate.append("rinvii")
        if self._fermo is not None:
            self._fermo.set()
        if self._esplodi:
            raise RuntimeError("boom")
        return 0

    def pulisci(self):
        self.chiamate.append("pulizia")
        return 0


def test_il_passo_fa_la_pulizia_anche_se_i_rinvii_esplodono():
    servizio = ServizioFinto(esplodi=True)
    cicli.passo(servizio)
    assert servizio.chiamate == ["rinvii", "pulizia"]


def test_il_pianificatore_si_ferma():
    fermo = threading.Event()
    servizio = ServizioFinto(fermo=fermo)
    cicli.ciclo_pianificatore(servizio, fermo, intervallo=0.001)
    assert servizio.chiamate == ["rinvii", "pulizia"]
    cicli.ciclo_pianificatore(servizio, fermo, intervallo=0.001)  # già fermo: niente
    assert servizio.chiamate == ["rinvii", "pulizia"]
