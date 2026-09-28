import json
import time

import pytest

from tests.finti import chiavi_push

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


def test_un_409_dopo_una_risposta_persa_non_diventa_foto_non_inviata(in_rete, pagina):
    """Il primo invio arriva al servizio ma la risposta si perde; Alberto accetta
    la foto; il tentativo automatico riceve 409. La foto del servizio è quella
    della pagina: è un successo, e nessun «Foto non inviata»."""
    giro_id = in_rete.servizio.apri_giro(in_rete.gio)["giro"]["id"]
    invii = []

    def risposta_persa(richiesta):
        invii.append(richiesta.request.method)
        if len(invii) > 1:
            richiesta.continue_()
            return
        richiesta.fetch()
        in_rete.servizio.decidi(giro_id, "emi", 1, "accettata", None)
        richiesta.abort()

    pagina.route(f"**/api/giro/{giro_id}/foto", risposta_persa)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    pagina.click("#scatta")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)
    pagina.click("#scatta-foto")
    pagina.click("#invia")
    schermata(pagina, "accettata").wait_for(state="visible")
    assert invii == ["PUT", "PUT"]
    assert pagina.locator("#avviso").is_hidden(), pagina.locator("#avviso").text_content()


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


def con_iscrizione_nel_browser(pagina, endpoint="https://push.example/e2e"):
    """Il permesso vero, concesso a Chrome; l'iscrizione finta, perché Chrome
    headless non ha un servizio push. Lo script entra dal protocollo di Chrome,
    non dalla pagina: la CSP non lo riguarda."""
    pagina.context.grant_permissions(["notifications"])
    iscrizione = json.dumps({"endpoint": endpoint, "keys": chiavi_push()})
    pagina.add_init_script(
        script=f"PushManager.prototype.getSubscription = async () => "
        f"({{ endpoint: {json.dumps(endpoint)}, toJSON: () => ({iscrizione}) }});"
    )


def test_all_apertura_l_iscrizione_del_browser_torna_al_servizio(in_rete, pagina):
    con_iscrizione_nel_browser(pagina)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "nessun_giro").wait_for(state="visible")
    assert aspetta(lambda: [i.endpoint for i in in_rete.store.iscrizioni_di("emi")] == ["https://push.example/e2e"])
    assert aspetta(lambda: pagina.locator("#notifiche").is_hidden())


def test_se_il_servizio_non_conferma_l_iscrizione_la_sezione_resta(in_rete, pagina):
    con_iscrizione_nel_browser(pagina)
    pagina.route("**/api/push", lambda richiesta: richiesta.fulfill(status=500))
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    pagina.locator("#attiva-notifiche").wait_for(state="visible")
    assert pagina.locator("#notifiche").is_visible()


def test_salta_rimanda_l_invito(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#salta")
    schermata(pagina, "rinviato").wait_for(state="visible")
    giro = in_rete.store.ultimo_giro()
    assert in_rete.store.rinvio(giro.id, "emi") is not None
