import time

import pytest

pytestmark = pytest.mark.e2e


def schermata(pagina, nome):
    return pagina.locator(f'[data-schermata="{nome}"]')


def aspetta(condizione, secondi=5):
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if condizione():
            return True
        time.sleep(0.05)
    return False


def test_senza_giro_la_pagina_lo_dice(in_rete, pagina):
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "nessun_giro").wait_for(state="visible")


def test_scatto_e_invio_fino_alla_foto_ricevuta(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    # wait_for_function con una stringa passa da eval, che la CSP della pagina
    # blocca (bene così): si interroga la pagina con evaluate, che non la attraversa.
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)
    pagina.click("#scatta-foto")
    schermata(pagina, "revisione").wait_for(state="visible")
    pagina.click("#invia")
    schermata(pagina, "in_attesa").wait_for(state="visible")
    giro = in_rete.store.ultimo_giro()
    assert in_rete.store.foto(giro.id, "emi").stato == "in_attesa"
    assert aspetta(lambda: in_rete.telegram.di_tipo("manda_foto"))


def test_l_avviso_di_rete_sparisce_quando_il_servizio_risponde(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.route("**/api/stato", lambda richiesta: richiesta.abort())
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    avviso = pagina.locator("#avviso")
    avviso.wait_for(state="visible")
    assert avviso.text_content() == "Non riesco a raggiungere il servizio: riprovo tra poco."
    pagina.unroute("**/api/stato")
    # Come allo sblocco del telefono; la pagina headless è visibile, quindi aggiorna.
    pagina.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    schermata(pagina, "invito").wait_for(state="visible")
    avviso.wait_for(state="hidden")


def test_salta_rimanda_l_invito(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#salta")
    schermata(pagina, "rinviato").wait_for(state="visible")
    giro = in_rete.store.ultimo_giro()
    assert in_rete.store.rinvio(giro.id, "emi") is not None
