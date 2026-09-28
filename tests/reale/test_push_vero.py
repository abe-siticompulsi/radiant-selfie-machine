"""Il servizio push vero. Contratto: le nostre chiavi VAPID, la cifratura e il
TTL sono accettati (201) dal servizio push dell'iscrizione. Che la notifica
compaia sullo schermo lo verifica una persona: il testo della notifica lo dice."""

import pytest
from py_vapid import Vapid

from rsm.push import Notificatore
from rsm.store import Store
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def test_il_servizio_push_accetta_la_nostra_firma():
    soprannome = richiesta("RSM_REALE_PUSH_A")
    store = Store(richiesta("RSM_DB"))
    iscrizioni = store.iscrizioni_di(soprannome)
    if not iscrizioni:
        pytest.fail(f"{soprannome} non ha iscrizioni push: attiva le notifiche dalla sua pagina")
    notificatore = Notificatore(
        store, Vapid.from_file(richiesta("RSM_VAPID_PEM")), richiesta("RSM_VAPID_CONTATTO")
    )
    accettati = notificatore.a_persona(
        soprannome, "🧪 Prova", "Se leggi questa notifica, il push funziona.", ttl=600
    )
    assert accettati == len(iscrizioni)
