import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from rsm import gettoni
from tests.finti import chiavi_push
from tests.immagini import jpeg

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
    # L'interruttore del conto è spento di partenza: lo scatto è immediato, senza numeri.
    _registra_i_numeri_del_conto(pagina)
    pagina.click("#scatta-foto")
    assert pagina.locator("#numero-conto").is_hidden()  # il gestore è sincrono: un conto sarebbe già partito
    schermata(pagina, "revisione").wait_for(state="visible")
    assert pagina.evaluate("window.numeriDelConto") == []
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


def _in_anteprima(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)


def _registra_i_numeri_del_conto(pagina):
    """Annota ogni numero che la pagina scrive in #numero-conto: la sequenza si
    legge alla fine, senza campionare a intervalli (che sarebbe instabile).
    `scrittiDelConto` annota anche se l'elemento era nascosto nell'istante preciso
    della scrittura: una regione aria-live che appare già piena non viene
    annunciata dai lettori di schermo, quindi deve essere visibile prima."""
    pagina.evaluate(
        """() => {
            window.numeriDelConto = [];
            window.scrittiDelConto = [];
            const numero = document.getElementById('numero-conto');
            new MutationObserver(() => window.numeriDelConto.push(numero.textContent))
                .observe(numero, { childList: true, characterData: true, subtree: true });
            const originale = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
            Object.defineProperty(numero, 'textContent', {
                configurable: true,
                get() { return originale.get.call(this); },
                set(testo) {
                    window.scrittiDelConto.push([testo, this.hidden]);
                    originale.set.call(this, testo);
                },
            });
        }"""
    )


def _rallenta_la_codifica(pagina, ms=1500):
    """La codifica del JPEG dopo lo zero dura pochi millisecondi: la si allunga per
    poter guardare la pagina mentre dura. `codificaIniziata` dice che è partita."""
    pagina.evaluate(
        """(ms) => {
            const originale = HTMLCanvasElement.prototype.toBlob;
            window.codificaIniziata = false;
            HTMLCanvasElement.prototype.toBlob = function (...argomenti) {
                window.codificaIniziata = true;
                setTimeout(() => originale.apply(this, argomenti), ms);
            };
        }""",
        ms,
    )


def test_il_conto_alla_rovescia_aspetta_tre_secondi_e_scatta(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    assert pagina.locator("#etichetta-conto").inner_text() == "Conto alla rovescia (3 secondi)"  # come in spec §3.3
    pagina.check("#interruttore-conto")
    _registra_i_numeri_del_conto(pagina)
    inizio = time.monotonic()
    pagina.click("#scatta-foto")
    numero = pagina.locator("#numero-conto")
    numero.wait_for(state="visible")
    assert pagina.locator("#ferma-conto").is_visible()
    assert not pagina.locator("#scatta-foto").is_visible()
    assert pagina.locator("#interruttore-conto").is_disabled()
    schermata(pagina, "revisione").wait_for(state="visible", timeout=6000)
    assert time.monotonic() - inizio >= 2.5
    assert pagina.evaluate("window.numeriDelConto") == ["3", "2", "1"]
    # Ogni numero, «3» compreso, si scrive quando l'elemento è già visibile.
    assert pagina.evaluate("window.scrittiDelConto") == [["3", False], ["2", False], ["1", False]]


def test_allo_zero_il_numero_e_ferma_spariscono_durante_la_codifica(in_rete, pagina):
    """Allo zero la foto è già scattata: mentre il JPEG si codifica non c'è più un
    «Ferma» da premere (porterebbe all'anteprima, e si finirebbe comunque in
    revisione), né un numero «1» che non è più vero."""
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    _rallenta_la_codifica(pagina)
    pagina.click("#scatta-foto")
    assert aspetta(lambda: pagina.evaluate("window.codificaIniziata"), secondi=6)
    assert pagina.locator("#numero-conto").is_hidden()
    assert pagina.locator("#ferma-conto").is_hidden()
    assert pagina.locator("#scatta-foto").is_hidden()
    assert not schermata(pagina, "revisione").is_visible()  # la codifica non è ancora finita
    schermata(pagina, "revisione").wait_for(state="visible", timeout=4000)


def test_se_la_pagina_va_sullo_sfondo_durante_la_codifica_si_resta_all_anteprima(in_rete, pagina):
    """Se la persona lascia la pagina dopo lo zero, il conto è fermato come sempre:
    la foto che si stava codificando non deve portare in revisione dopo."""
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    _rallenta_la_codifica(pagina)
    pagina.click("#scatta-foto")
    assert aspetta(lambda: pagina.evaluate("window.codificaIniziata"), secondi=6)
    pagina.evaluate(
        "Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});"
        "document.dispatchEvent(new Event('visibilitychange'))"
    )
    time.sleep(2.5)  # oltre la codifica rallentata
    assert schermata(pagina, "anteprima").is_visible()
    assert not schermata(pagina, "revisione").is_visible()


def test_ferma_riporta_all_anteprima_senza_scattare(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    pagina.click("#ferma-conto")
    pagina.locator("#numero-conto").wait_for(state="hidden")
    assert pagina.locator("#scatta-foto").is_visible()
    assert pagina.evaluate("document.getElementById('video').videoWidth") > 0  # la fotocamera resta accesa
    time.sleep(3.5)  # oltre i tre secondi: il timer fermato non deve scattare
    assert schermata(pagina, "anteprima").is_visible()
    assert not schermata(pagina, "revisione").is_visible()


def _riquadro(pagina, selettore):
    riquadro = pagina.locator(selettore).bounding_box()
    assert riquadro is not None, f"{selettore} non è visibile"
    return riquadro


@pytest.mark.parametrize("viewport", [None, {"width": 375, "height": 812}], ids=["larghezza-di-default", "375px"])
def test_ferma_occupa_il_posto_di_scatta_la_foto(in_rete, pagina, viewport):
    """Un tocco dove stava «Scatta la foto» deve cadere su «Ferma», non su «Annulla»
    (che esce dal conto e spegne la fotocamera): i riquadri devono coincidere."""
    if viewport:
        pagina.set_viewport_size(viewport)
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    scatta, annulla = _riquadro(pagina, "#scatta-foto"), _riquadro(pagina, "#annulla")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    ferma, annulla_nel_conto = _riquadro(pagina, "#ferma-conto"), _riquadro(pagina, "#annulla")
    for lato in ("x", "y", "width", "height"):
        assert ferma[lato] == pytest.approx(scatta[lato], abs=1), f"«Ferma» non sta dov'era «Scatta la foto»: {lato}"
        assert annulla_nel_conto[lato] == pytest.approx(annulla[lato], abs=1), f"«Annulla» si è spostato: {lato}"


def test_l_interruttore_si_ricorda_sul_dispositivo(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.reload()
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert pagina.locator("#interruttore-conto").is_checked()


def test_se_a_meta_conto_la_foto_viene_accettata_non_si_scatta(in_rete, pagina):
    """Il servizio cambia stato durante il conto (qui Alberto accetta la foto che
    il giocatore sta rifacendo): la pagina mostra l'accettazione, il timer si
    ferma, e allo zero non compare nessun avviso falso sulla fotocamera."""
    in_rete.servizio.apri_giro(in_rete.gio)
    emi = in_rete.store.persona_da_impronta(gettoni.impronta(in_rete.emi))
    ricevuta = in_rete.servizio.ricevi_foto(emi, in_rete.store.ultimo_giro().id, jpeg())
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "in_attesa").wait_for(state="visible")
    pagina.click("#rifai-in-attesa")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    in_rete.servizio.decidi(ricevuta.foto.giro_id, "emi", ricevuta.foto.versione, "accettata", None)
    pagina.evaluate("document.dispatchEvent(new Event('visibilitychange'))")  # rilegge lo stato
    schermata(pagina, "accettata").wait_for(state="visible")
    time.sleep(3.5)  # oltre lo zero del conto
    assert schermata(pagina, "accettata").is_visible()
    assert not pagina.locator("#avviso").is_visible()


def test_l_interruttore_spento_si_ricorda_spento(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.reload()
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert pagina.locator("#interruttore-conto").is_checked()
    pagina.uncheck("#interruttore-conto")
    pagina.reload()
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert not pagina.locator("#interruttore-conto").is_checked()


def test_annulla_durante_il_conto_torna_all_invito_senza_scattare(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    pagina.click("#annulla")
    schermata(pagina, "invito").wait_for(state="visible")
    time.sleep(4)  # oltre i tre secondi: il conto annullato non deve scattare
    assert schermata(pagina, "invito").is_visible()
    assert not schermata(pagina, "revisione").is_visible()


def test_pagina_sullo_sfondo_a_meta_conto_ferma_il_conto(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    # Il Chrome dei test è sempre visibile: si simula il passaggio sullo sfondo.
    pagina.evaluate(
        "Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});"
        "document.dispatchEvent(new Event('visibilitychange'))"
    )
    pagina.locator("#numero-conto").wait_for(state="hidden")
    assert schermata(pagina, "anteprima").is_visible()
    assert pagina.locator("#scatta-foto").is_visible()
    time.sleep(4)  # oltre i tre secondi: il conto fermato non deve scattare
    assert schermata(pagina, "anteprima").is_visible()
    assert not schermata(pagina, "revisione").is_visible()


def test_un_doppio_tocco_su_ferma_non_fa_ripartire_il_conto(in_rete, pagina):
    """«Ferma» sta dove stava «Scatta la foto»: il secondo tocco di un doppio tocco
    cade sul pulsante dello scatto e non deve far ripartire il conto."""
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    pagina.dblclick("#ferma-conto")
    time.sleep(4)  # oltre i tre secondi: un conto ripartito avrebbe già scattato
    assert schermata(pagina, "anteprima").is_visible()
    assert pagina.locator("#numero-conto").is_hidden()
    assert not schermata(pagina, "revisione").is_visible()
    # La pausa scade: passato mezzo secondo, un tocco su «Scatta la foto» conta.
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible", timeout=2000)


def test_l_avviso_di_fotocamera_non_pronta_non_resta_dopo_uno_scatto_riuscito(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    # La fotocamera perde l'immagine a metà conto: allo zero non c'è niente da scattare.
    pagina.evaluate("document.getElementById('video').srcObject = null")
    assert pagina.evaluate("document.getElementById('video').videoWidth") == 0
    avviso = pagina.locator("#avviso")
    avviso.wait_for(state="visible", timeout=6000)
    assert avviso.text_content() == "La fotocamera non è ancora pronta: riprova."
    assert schermata(pagina, "anteprima").is_visible()
    assert pagina.locator("#scatta-foto").is_visible()
    # Si riaccende la fotocamera (Annulla, poi Scatta) e si scatta davvero.
    pagina.click("#annulla")
    schermata(pagina, "invito").wait_for(state="visible")
    assert avviso.is_hidden(), avviso.text_content()  # sull'invito l'avviso non descrive più la schermata
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    assert avviso.is_hidden(), avviso.text_content()  # un nuovo scatto toglie l'avviso vecchio
    schermata(pagina, "revisione").wait_for(state="visible", timeout=6000)
    assert avviso.is_hidden(), avviso.text_content()


def _chiudi_il_giro(in_rete):
    """Come quando il giro scade o il master ne apre uno nuovo, ma subito: il
    servizio lo dà per chiuso."""
    in_rete.store.chiudi_giro(in_rete.store.ultimo_giro().id, datetime.now(UTC) - timedelta(seconds=1))


def _rileggi_lo_stato(pagina):
    """Come al ritorno sulla pagina, o al polling: la pagina rilegge lo stato."""
    pagina.evaluate("document.dispatchEvent(new Event('visibilitychange'))")


def _invito_con_la_fotocamera_spenta(pagina):
    """La persona non ha chiesto la fotocamera in questo giro: invito, e niente video."""
    schermata(pagina, "invito").wait_for(state="visible", timeout=3000)
    assert not schermata(pagina, "anteprima").is_visible()
    assert pagina.evaluate("document.getElementById('video').srcObject") is None  # fotocamera spenta


def _riparte_dall_invito(in_rete, pagina):
    """Il giro si chiude con la pagina aperta e se ne apre uno nuovo: la persona
    non ha chiesto la fotocamera, quindi ricompare l'invito e la fotocamera è spenta."""
    _chiudi_il_giro(in_rete)
    _rileggi_lo_stato(pagina)
    schermata(pagina, "nessun_giro").wait_for(state="visible", timeout=3000)
    in_rete.servizio.apri_giro(in_rete.gio)
    _rileggi_lo_stato(pagina)
    _invito_con_la_fotocamera_spenta(pagina)


def _chiudi_e_riapri_il_giro(in_rete):
    """Come «Apri il giro» a più di 12 ore dal precedente: il vecchio si chiude e
    ne nasce uno nuovo nello stesso blocco, senza che la pagina rilegga in mezzo
    (il polling non vede mai «nessun giro»). Restituisce i numeri dei due giri."""
    vecchio = in_rete.store.ultimo_giro().id
    _chiudi_il_giro(in_rete)
    nuovo = in_rete.servizio.apri_giro(in_rete.gio)["giro"]["id"]
    assert nuovo != vecchio
    return vecchio, nuovo


def test_se_a_meta_conto_il_giro_si_chiude_con_un_giro_nuovo_si_riparte_dall_invito(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    _riparte_dall_invito(in_rete, pagina)


def test_se_nell_anteprima_il_giro_si_chiude_con_un_giro_nuovo_si_riparte_dall_invito(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    _riparte_dall_invito(in_rete, pagina)


def test_un_guasto_di_rete_nell_anteprima_non_butta_fuori_dall_anteprima(in_rete, pagina):
    """Un aggiornamento che non riesce non dice niente sul servizio: lo stato
    precedente resta, e con lui l'anteprima e la fotocamera accesa."""
    _in_anteprima(in_rete, pagina)
    pagina.route("**/api/stato", lambda richiesta: richiesta.abort())
    _rileggi_lo_stato(pagina)
    pagina.locator("#avviso").wait_for(state="visible")
    assert schermata(pagina, "anteprima").is_visible()
    assert pagina.evaluate("document.getElementById('video').videoWidth") > 0


def test_se_nell_anteprima_il_giro_cambia_senza_che_la_pagina_lo_veda_si_riparte_dall_invito(in_rete, pagina):
    """Il caso delle 12 ore: il giro vecchio si chiude e il nuovo si apre nello
    stesso blocco. La fase locale appartiene al giro in cui è cominciata: la
    pagina non resta nell'anteprima, e la fotocamera si spegne."""
    _in_anteprima(in_rete, pagina)
    _chiudi_e_riapri_il_giro(in_rete)
    _rileggi_lo_stato(pagina)
    _invito_con_la_fotocamera_spenta(pagina)


def test_se_a_meta_conto_il_giro_cambia_senza_che_la_pagina_lo_veda_si_riparte_dall_invito(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    _chiudi_e_riapri_il_giro(in_rete)
    _rileggi_lo_stato(pagina)
    _invito_con_la_fotocamera_spenta(pagina)
    time.sleep(4)  # oltre i tre secondi: il conto di un giro che non c'è più non deve scattare
    assert schermata(pagina, "invito").is_visible()
    assert not schermata(pagina, "revisione").is_visible()
    assert pagina.locator("#numero-conto").is_hidden()


def test_se_nella_revisione_il_giro_cambia_la_foto_vecchia_non_va_nel_giro_nuovo(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.click("#scatta-foto")
    schermata(pagina, "revisione").wait_for(state="visible")
    vecchio, nuovo = _chiudi_e_riapri_il_giro(in_rete)
    _rileggi_lo_stato(pagina)
    _invito_con_la_fotocamera_spenta(pagina)
    assert not schermata(pagina, "revisione").is_visible()
    # La persona riparte da capo: la foto nuova, scattata nel giro nuovo, va nel giro nuovo.
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)
    pagina.click("#scatta-foto")
    schermata(pagina, "revisione").wait_for(state="visible")
    pagina.click("#invia")
    schermata(pagina, "in_attesa").wait_for(state="visible")
    assert in_rete.store.foto(nuovo, "emi").stato == "in_attesa"
    assert in_rete.store.foto(vecchio, "emi") is None


def test_un_invio_ritentato_dopo_un_5xx_va_ancora_al_giro_in_cui_la_foto_e_stata_scattata(in_rete, pagina):
    """Il primo tentativo fallisce (5xx) e, mentre la pagina aspetta il secondo, il
    servizio passa a un giro nuovo che la pagina vede. L'invio non si interrompe,
    ma il giro lo decide la foto, non lo stato di adesso: il secondo tentativo va al
    giro vecchio (che risponde 410), mai al nuovo."""
    _in_anteprima(in_rete, pagina)
    pagina.click("#scatta-foto")
    schermata(pagina, "revisione").wait_for(state="visible")
    vecchio = in_rete.store.ultimo_giro().id
    nuovo = []
    richieste = []
    pagina.on("request", lambda r: richieste.append(f"{r.method} {r.url.split('/api/')[1]}") if "/api/" in r.url else None)

    def primo_tentativo_fallisce(richiesta):
        if not nuovo:
            nuovo.append(_chiudi_e_riapri_il_giro(in_rete)[1])
            _rileggi_lo_stato(pagina)
            richiesta.fulfill(status=500, body="errore")
        else:
            richiesta.continue_()

    pagina.route("**/api/giro/*/foto", primo_tentativo_fallisce)
    pagina.click("#invia")
    _invito_con_la_fotocamera_spenta(pagina)  # 410 del giro vecchio: «respinta», e l'invito del giro nuovo
    posizioni = [i for i, r in enumerate(richieste) if r.startswith("PUT")]
    assert [richieste[i] for i in posizioni] == [f"PUT giro/{vecchio}/foto"] * 2
    # La pagina ha visto il giro nuovo fra i due tentativi: senza il legame al giro andrebbe lì.
    assert "GET stato" in richieste[posizioni[0] : posizioni[1]]
    assert in_rete.store.foto(nuovo[0], "emi") is None
    assert in_rete.store.foto(vecchio, "emi") is None
    assert pagina.locator("#avviso").text_content() == "Foto non inviata: il giro è chiuso."


_GUASTI_DELLA_CODIFICA = {
    "toblob-lancia": "HTMLCanvasElement.prototype.toBlob = function () { throw new Error('guasto'); };",
    "toblob-nullo": "HTMLCanvasElement.prototype.toBlob = function (richiamo) { richiamo(null); };",
    "toblob-muto": "HTMLCanvasElement.prototype.toBlob = function () { window.codificaIniziata = true; };",
    "drawimage-lancia": "CanvasRenderingContext2D.prototype.drawImage = function () { throw new Error('guasto'); };",
}


def _guasta_la_codifica(pagina, guasto):
    """Fa fallire la codifica della foto come potrebbe farla fallire il browser
    (memoria, tela troppo grande): `toBlob` che lancia, che dà null o che non
    risponde mai, oppure `drawImage` che lancia. `_ripara_la_codifica` rimette il
    `toBlob` vero."""
    pagina.evaluate(
        "() => { window.codificaIniziata = false; window.toBlobVero = HTMLCanvasElement.prototype.toBlob; "
        + _GUASTI_DELLA_CODIFICA[guasto]
        + " }"
    )


def _ripara_la_codifica(pagina):
    pagina.evaluate("() => { HTMLCanvasElement.prototype.toBlob = window.toBlobVero; }")


@pytest.mark.parametrize(
    ("guasto", "con_conto"),
    [
        ("toblob-lancia", False),
        ("toblob-lancia", True),
        ("toblob-nullo", False),
        ("toblob-nullo", True),
        ("drawimage-lancia", False),
    ],
    ids=["toBlob-lancia", "toBlob-lancia-con-conto", "toBlob-nullo", "toBlob-nullo-con-conto", "drawImage-lancia"],
)
def test_se_la_codifica_della_foto_fallisce_si_resta_all_anteprima_con_un_avviso(in_rete, pagina, guasto, con_conto):
    """Un errore del browser nella codifica non lascia la pagina a metà: niente
    revisione con una foto che non c'è, l'avviso lo dice, e si può riprovare."""
    _in_anteprima(in_rete, pagina)
    if con_conto:
        pagina.check("#interruttore-conto")
    _guasta_la_codifica(pagina, guasto)
    pagina.click("#scatta-foto")
    avviso = pagina.locator("#avviso")
    avviso.wait_for(state="visible", timeout=6000)  # con il conto, dopo i tre secondi
    assert avviso.text_content() == "Non sono riuscito a fare la foto: riprova."
    assert schermata(pagina, "anteprima").is_visible()
    assert pagina.locator("#scatta-foto").is_visible()
    assert pagina.locator("#ferma-conto").is_hidden()
    assert pagina.locator("#numero-conto").is_hidden()
    assert not schermata(pagina, "revisione").is_visible()


def test_se_la_codifica_non_risponde_mai_il_conto_seguente_mostra_numero_e_ferma(in_rete, pagina):
    """Allo zero `toBlob` non risponde: restano solo «Annulla». Il conto che si fa
    dopo (la codifica è tornata a funzionare) deve mostrare numero e «Ferma» come
    sempre, non ereditare lo stato «sto codificando» del tentativo rimasto in sospeso."""
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    _guasta_la_codifica(pagina, "toblob-muto")
    pagina.click("#scatta-foto")
    assert aspetta(lambda: pagina.evaluate("window.codificaIniziata"), secondi=6)
    assert pagina.locator("#numero-conto").is_hidden()
    pagina.click("#annulla")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)
    _ripara_la_codifica(pagina)
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible", timeout=2000)
    assert pagina.locator("#ferma-conto").is_visible()
    schermata(pagina, "revisione").wait_for(state="visible", timeout=6000)
