"""Le variabili del piano reale.

Una variabile mancante fa saltare il test, e il messaggio dice quale contratto
resta non verificato. Un salto non è un successo: il piano reale è verde solo
quando non salta niente (`pytest -rs` elenca i salti con il loro motivo).
"""

import os

import pytest


def richiesta(nome: str) -> str:
    valore = os.environ.get(nome, "").strip()
    if not valore:
        pytest.skip(f"{nome} non impostata: questo contratto NON è stato verificato")
    return valore
