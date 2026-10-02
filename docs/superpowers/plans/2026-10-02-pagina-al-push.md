# La pagina aperta rilegge lo stato all'arrivo di un push — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando arriva un push, la pagina personale aperta rilegge subito lo stato del servizio, invece di aspettare il controllo dei 20 secondi.

**Architecture:** Il servizio non cambia: manda il push dopo aver salvato lo stato, quindi rileggerlo all'arrivo del push basta. Nel gestore `push`, il service worker (`web/sw.js`) mostra la notifica come oggi e, in parallelo, manda `{ tipo: 'push' }` alle finestre aperte nel suo ambito, cioè la pagina di quella persona. La pagina (`web/static/app.js`) ascolta i messaggi del service worker e, a `{ tipo: 'push' }`, chiama `aggiorna()`: la stessa funzione del controllo periodico e del ritorno in primo piano. I 20 secondi restano come rete di sicurezza.

**Tech Stack:** JavaScript senza framework né build. Le prove da capo a fondo usano Playwright con il Chrome installato (`-m e2e`); il push lo consegna il protocollo di Chrome (`ServiceWorker.deliverPushMessage`), come il pulsante «Push» degli strumenti per sviluppatori.

**Spec:** `docs/superpowers/specs/2026-09-27-radiant-selfie-machine-design.md`, §3 punto 2, §4 (`sw.js`) e §11 (polling), commit 03437f4.

## Global Constraints

- **Italiano** in ogni testo per le persone, nei commenti e nei nomi nuovi. Commit in inglese e brevi, con una riga `Co-Authored-By:` che nomina il modello che fa il commit.
- **Ogni messaggio afferma solo ciò che è stato verificato.** Il push non porta lo stato: la pagina lo rilegge dal servizio, e la schermata la decide `schermata()` come sempre.
- **La notifica compare comunque**, anche con la pagina davanti: Chrome e Safari chiedono che ogni push ne mostri una. Un errore nel mostrarla non impedisce di avvisare la pagina, e viceversa.
- **Solo le finestre di quella persona:** il service worker avvisa solo le finestre il cui indirizzo comincia con il suo ambito (`/p/<gettone>/`), come già fa al tocco sulla notifica.
- **La pagina gira sotto una Content-Security-Policy severa:** niente script o stili in linea, niente `eval`. Niente dipendenze npm. Nelle prove, `evaluate` sì; `wait_for_function` con una stringa no, perché la CSP lo blocca.
- **La suite veloce resta veloce;** le prove in Chrome restano sotto `-m e2e`.
- **Ramo:** `pagina-al-push`, da `main`. Non si fonde senza l'assenso di Alberto.

## Struttura dei file

| file | responsabilità |
|---|---|
| `web/sw.js` (modifica) | `finestreDellaPersona()`, usata dal tocco sulla notifica e dal push; il gestore `push` avvisa le pagine |
| `web/static/app.js` (modifica) | ascolta i messaggi del service worker e rilegge lo stato |
| `tests/e2e/test_pagina.py` (modifica) | `_consegna_un_push()` e la prova della pagina che cambia subito |
| `docs/differenze-fra-test-e-realta.md` (modifica) | una riga nella tabella e una voce nei controlli a mano |

---

### Task 1: il push fa rileggere lo stato alla pagina aperta

**Files:**
- Modify: `web/sw.js` (gestori `push` e `notificationclick`)
- Modify: `web/static/app.js` (sezione `// --- notifiche`, e l'avvio in fondo al file)
- Modify: `tests/e2e/test_pagina.py` (dopo `test_se_il_servizio_non_conferma_l_iscrizione_la_sezione_resta`)
- Modify: `docs/differenze-fra-test-e-realta.md`

**Interfaces:**
- Consumes: `aggiorna()` in `app.js`, che legge `/api/stato` e chiama `disegna()`. `Servizio.decidi(giro_id, soprannome, versione, esito, motivo)` in `src/rsm/servizio.py`, `Servizio.ricevi_foto(persona, giro_id, jpeg)`, `Store.persona_da_impronta(...)`, e le fixture `in_rete` e `pagina` di `tests/e2e/conftest.py`.
- Produces: il messaggio `{ tipo: 'push' }` dal service worker alla pagina. Nessuna API nuova del servizio.

- [ ] **Step 0: il ramo**

```bash
git switch -c pagina-al-push
```

- [ ] **Step 1: scrivi la prova che fallisce**

In `tests/e2e/test_pagina.py` (gli import che servono, `json`, `gettoni` e `jpeg`, ci sono già), dopo `test_se_il_servizio_non_conferma_l_iscrizione_la_sezione_resta`:

```python
def _consegna_un_push(pagina, origine, dati):
    """Il push vero, consegnato al service worker dal protocollo di Chrome: è il
    pulsante «Push» degli strumenti per sviluppatori. Chrome headless non ha un
    servizio push, ma il service worker riceve l'evento come da un servizio vero.
    Gli eventi del protocollo arrivano solo mentre Playwright lavora: per questo
    si aspetta con wait_for_timeout, non con time.sleep."""
    assert aspetta(lambda: pagina.evaluate("!!navigator.serviceWorker.controller"))
    cdp = pagina.context.new_cdp_session(pagina)
    registrazioni = []
    cdp.on("ServiceWorker.workerRegistrationUpdated", lambda evento: registrazioni.extend(evento["registrations"]))
    cdp.send("ServiceWorker.enable")
    for _ in range(100):
        nostre = [r for r in registrazioni if r["scopeURL"] == pagina.url and not r.get("isDeleted")]
        if nostre:
            break
        pagina.wait_for_timeout(50)
    assert nostre, f"nessuna registrazione del service worker per {pagina.url}: {registrazioni}"
    cdp.send(
        "ServiceWorker.deliverPushMessage",
        {"origin": origine, "registrationId": nostre[0]["registrationId"], "data": json.dumps(dati)},
    )


def test_all_arrivo_di_un_push_la_pagina_rilegge_subito_lo_stato(in_rete, pagina):
    """Alberto chiede un'altra foto: il servizio salva la decisione e manda il push.
    La pagina aperta la mostra subito, non al controllo dei 20 secondi."""
    pagina.context.grant_permissions(["notifications"])
    in_rete.servizio.apri_giro(in_rete.gio)
    emi = in_rete.store.persona_da_impronta(gettoni.impronta(in_rete.emi))
    ricevuta = in_rete.servizio.ricevi_foto(emi, in_rete.store.ultimo_giro().id, jpeg())
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "in_attesa").wait_for(state="visible")
    in_rete.servizio.decidi(ricevuta.foto.giro_id, "emi", ricevuta.foto.versione, "da_rifare", "troppo buia")
    _consegna_un_push(
        pagina, in_rete.url, {"titolo": "Alberto chiede un'altra foto", "testo": "troppo buia"}
    )
    # Molto meno dei 20 secondi del controllo periodico, cominciato al caricamento.
    schermata(pagina, "nuova_richiesta").wait_for(state="visible", timeout=3000)
    assert "troppo buia" in pagina.locator("#motivo").inner_text()
```

`in_rete.url` è già l'origine del servizio di prova (`http://127.0.0.1:<porta>`, senza barra finale: `tests/e2e/conftest.py`), quindi va bene così com'è per `deliverPushMessage`. Le parti del protocollo di Chrome usate qui sono state provate in Chrome headless prima di scrivere il piano: la registrazione si trova, e il service worker riceve il push.

- [ ] **Step 2: lancia la prova e verifica che fallisce**

Run: `uv run pytest -m e2e -k rilegge_subito -q`
Expected: FAIL, con un timeout di `wait_for` su `[data-schermata="nuova_richiesta"]`: senza la modifica la pagina resta su «in attesa» fino al controllo dei 20 secondi. Se invece fallisce prima, in `_consegna_un_push` (nessuna registrazione, o `deliverPushMessage` rifiutato), fermati e riportalo: la prova non sta ancora provando la cosa giusta.

- [ ] **Step 3: il service worker avvisa la pagina**

In `web/sw.js`, sostituisci i gestori `push` e `notificationclick` con:

```js
// Le finestre aperte di questa persona: quelle il cui indirizzo comincia con
// l'ambito del service worker, /p/<gettone>/. Le altre pagine della stessa
// origine (un'altra persona sullo stesso browser) non c'entrano.
async function finestreDellaPersona() {
  const finestre = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  return finestre.filter((finestra) => finestra.url.startsWith(self.registration.scope));
}

// Il servizio manda il push dopo aver salvato lo stato: la pagina aperta lo
// rilegge subito, senza aspettare il controllo dei 20 secondi.
async function avvisaLePagine() {
  for (const finestra of await finestreDellaPersona()) finestra.postMessage({ tipo: 'push' });
}

self.addEventListener('push', (evento) => {
  let dati = { titolo: 'Radiant Selfie Machine', testo: '' };
  try {
    dati = evento.data.json();
  } catch {
    // un push senza JSON mostra comunque il titolo
  }
  // La notifica compare comunque, anche con la pagina davanti: Chrome e Safari
  // chiedono che ogni push ne mostri una. Un errore in una delle due cose non
  // ferma l'altra.
  evento.waitUntil(
    Promise.allSettled([
      self.registration.showNotification(dati.titolo, {
        body: dati.testo,
        icon: '/static/icona-192.png',
        tag: 'radiant-selfie-machine',
        renotify: true,
      }),
      avvisaLePagine(),
    ]),
  );
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil(
    (async () => {
      const [finestra] = await finestreDellaPersona();
      if (finestra) return finestra.focus();
      return self.clients.openWindow(self.registration.scope);
    })(),
  );
});
```

Aggiorna anche il commento in cima al file: oltre a mostrare la notifica, il service worker avvisa la pagina aperta.

- [ ] **Step 4: la pagina ascolta**

In `web/static/app.js`, nella sezione `// --- notifiche`, subito dopo `registraServiceWorker()`:

```js
// Il service worker avvisa all'arrivo di un push (sw.js): lo stato nuovo è già
// salvato, e la pagina lo rilegge subito invece di aspettare i 20 secondi.
function ascoltaIlServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.addEventListener('message', (evento) => {
    if (evento.data?.tipo === 'push') aggiorna();
  });
}
```

E nell'avvio in fondo al file, prima di `await registraServiceWorker();`:

```js
ascoltaIlServiceWorker();
```

- [ ] **Step 5: lancia la prova e verifica che passa**

Run: `uv run pytest -m e2e -k rilegge_subito -q`
Expected: `1 passed`.

Poi la mutazione, per essere certi che la prova morde: togli temporaneamente `avvisaLePagine(),` dal `Promise.allSettled` in `web/sw.js` e rilancia. Atteso: FAIL. Ripristina (`git diff web/sw.js` deve mostrare solo la modifica dello Step 3).

- [ ] **Step 6: documenti**

In `docs/differenze-fra-test-e-realta.md`:

1. Nella tabella, dopo la riga che comincia con «Il push arriva sempre (`NotificheFinte`)», aggiungi:

```markdown
| Nella prova in Chrome il push lo consegna il protocollo di Chrome (`ServiceWorker.deliverPushMessage`) al service worker, subito. | Lo consegna il servizio push del browser, quando vuole: può arrivare in ritardo o mai. Per questo il controllo dei 20 secondi resta. | `tests/e2e/test_pagina.py::test_all_arrivo_di_un_push_la_pagina_rilegge_subito_lo_stato`; a mano, con la pagina aperta (voce qui sotto). |
```

2. Nella sezione «Da controllare a mano sul telefono», nel gruppo che meglio si presta (o in un gruppo «Notifiche», se non c'è), aggiungi:

```markdown
- Pagina aperta e notifiche attive (Chrome, Firefox, l'app sulla schermata Home dell'iPhone): Alberto chiede un'altra foto con un motivo. La notifica compare e, insieme, la pagina mostra la richiesta con il motivo, senza aspettare.
```

- [ ] **Step 7: tutte le suite**

Run, nell'ordine:
- `uv run pytest -q` → tutte passano (261 oggi).
- `node --test "web/test/*.test.js"` → 37 pass.
- `uv run ruff check src tests strumenti` → pulito.
- `uv run pytest -m e2e -q` → tutte passano (47 oggi, 48 con la nuova).
- `uv run pytest -m e2e -k rilegge_subito -q` tre volte di fila → `1 passed` ogni volta.

- [ ] **Step 8: commit**

```bash
git add web/sw.js web/static/app.js tests/e2e/test_pagina.py docs/differenze-fra-test-e-realta.md
git commit -m "page: re-read the state as soon as a push arrives

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

## Aggiunta durante l'esecuzione

La revisione del Task 1 ha notato che `aggiorna()` applicava ogni risposta, anche una
arrivata dopo una più recente: con il push le letture si sovrappongono più spesso, e
una lettura lenta partita prima della decisione poteva riportare la pagina allo stato
vecchio fino al controllo seguente. Ora una risposta vale solo se la lettura è partita
dopo quella già applicata, e l'errore di una lettura vecchia non mostra l'avviso di
rete. Prova: `test_una_lettura_vecchia_che_arriva_tardi_non_riporta_indietro_la_pagina`
(due varianti, «risponde» e «fallisce»), RED prima della correzione, e una mutazione
per ciascuna delle due condizioni.
