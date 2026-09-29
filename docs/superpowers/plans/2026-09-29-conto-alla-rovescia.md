# Conto alla rovescia prima dello scatto — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un interruttore nell'anteprima, «Conto alla rovescia (3 secondi)», ricordato sul dispositivo: acceso, «Scatta la foto» mostra 3, 2, 1 sopra l'anteprima e poi scatta.

**Architecture:** Tutto nella pagina; il servizio non cambia. La macchina a stati (`web/static/stati.js`) guadagna la fase locale `conto`, fra `anteprima` e `revisione`, che `schermata()` mostra come anteprima con `conto: true`, così la fotocamera resta accesa. La preferenza si legge e si scrive con due funzioni pure che ricevono l'archivio del browser, e un archivio che rifiuta vale «spento». `app.js` collega il timer, il numero sopra l'anteprima, il pulsante «Ferma» e l'interruttore.

**Tech Stack:** JavaScript senza framework né build; `node --test` per `stati.js`; Playwright con il Chrome installato per le prove da capo a fondo (`-m e2e`).

**Spec:** `docs/superpowers/specs/2026-09-27-radiant-selfie-machine-design.md`, §3.3 (commit 47f57d1), §4 e §11.

## Global Constraints

- **Italiano** in ogni testo per le persone, nei commenti e nei nomi nuovi. Commit in inglese e brevi, con una riga `Co-Authored-By:` che nomina il modello che fa il commit.
- **Tre secondi, spento di partenza**, ricordato nel browser di quel dispositivo; il servizio non ne sa nulla. Se il browser non può salvarlo, l'interruttore vale per la sessione della pagina.
- **Muto.** Nessun suono: il microfono dei giocatori è aperto su Discord e Craig registra.
- **Durante il conto:** «Scatta la foto» diventa «Ferma» (torna all'anteprima, fotocamera accesa); «Annulla» esce come sempre; l'interruttore non si tocca.
- **Pagina sullo sfondo a metà conto:** il conto si ferma e si torna all'anteprima. **Fotocamera senza immagine allo zero:** si torna all'anteprima con «La fotocamera non è ancora pronta: riprova».
- **Ogni messaggio afferma solo ciò che è stato verificato.** Nessuna foto finta, nessuno scatto che la persona non vede.
- **La pagina gira sotto una Content-Security-Policy severa:** niente script o stili in linea, niente `eval`. Niente dipendenze npm.
- **La suite veloce resta veloce;** le prove in Chrome restano sotto `-m e2e`.
- **Ramo:** `servizio-e-pagina`. Non si fonde senza l'assenso di Alberto.

## Struttura dei file

| file | responsabilità |
|---|---|
| `web/static/stati.js` (modifica) | la fase `conto`, `SECONDI_CONTO`, la preferenza (`leggiPreferenzaConto`, `salvaPreferenzaConto`) |
| `web/test/stati.test.js` (modifica) | le transizioni del conto, la schermata durante il conto, la preferenza con un archivio finto e uno ostile |
| `web/index.html` (modifica) | nell'anteprima: il numero sopra il video, «Ferma», l'interruttore |
| `web/static/stile.css` (modifica) | il numero sopra il video, l'interruttore |
| `web/static/app.js` (modifica) | il timer, «Ferma», l'interruttore ricordato, lo stop quando la pagina va sullo sfondo |
| `tests/e2e/test_pagina.py` (modifica) | tre prove in Chrome |
| `docs/differenze-fra-test-e-realta.md` (modifica) | una riga: nei test la pagina non va mai sullo sfondo |

---

### Task 1: la fase «conto» e la preferenza, in `stati.js`

**Files:**
- Modify: `web/static/stati.js` (la tabella `TRANSIZIONI`, `schermata`, e tre esportazioni nuove in fondo)
- Test: `web/test/stati.test.js`

**Interfaces:**
- Consumes: `dopo`, `schermata`, `FASE_INIZIALE` già in `stati.js`.
- Produces: eventi nuovi per `dopo`: `conta` (da `anteprima` a `conto`), e da `conto`: `scattata` → `revisione`, `ferma` → `anteprima`, `annulla` → `riposo`, `negata` → `fotocamera_negata`. `schermata(server, { fase: 'conto' }, ora)` restituisce `{ nome: 'anteprima', conto: true }` (una foto accettata vince comunque). `SECONDI_CONTO = 3`. `leggiPreferenzaConto(archivio) -> boolean` e `salvaPreferenzaConto(archivio, acceso: boolean) -> boolean` (se è stata salvata), dove `archivio` è `localStorage` o `null`.

- [ ] **Step 1: scrivi i test**

In `web/test/stati.test.js`, aggiungi i tre nomi nuovi all'import (in ordine alfabetico: `SECONDI_CONTO` dopo `FASE_INIZIALE`, `leggiPreferenzaConto` dopo `esitoDopoConflitto`, `salvaPreferenzaConto` dopo `msAllaFineDelRinvio`), poi aggiungi in fondo al file:

```js
test('il conto alla rovescia è una fase fra anteprima e revisione', () => {
  assert.equal(dopo(in_fase('anteprima'), 'conta').fase, 'conto');
  assert.equal(dopo(in_fase('conto'), 'scattata').fase, 'revisione');
  assert.equal(dopo(in_fase('conto'), 'ferma').fase, 'anteprima');
  assert.equal(dopo(in_fase('conto'), 'annulla').fase, 'riposo');
  assert.equal(dopo(in_fase('conto'), 'negata').fase, 'fotocamera_negata');
});

test('il conto parte solo dall\'anteprima, e una volta sola', () => {
  assert.throws(() => dopo(FASE_INIZIALE, 'conta'), /non ammesso/);
  assert.throws(() => dopo(in_fase('conto'), 'conta'), /non ammesso/);
});

test('durante il conto la schermata resta l\'anteprima, così la fotocamera non si spegne', () => {
  const s = stato({ foto: { stato: 'in_attesa', sha256: 'x', motivo: null } });
  assert.deepEqual(schermata(s, in_fase('conto'), ORA), { nome: 'anteprima', conto: true });
  assert.deepEqual(schermata(s, in_fase('anteprima'), ORA), { nome: 'anteprima' });
});

test('una foto accettata vince anche sul conto', () => {
  const s = stato({ foto: { stato: 'accettata', sha256: 'x', motivo: null } });
  assert.equal(schermata(s, in_fase('conto'), ORA).nome, 'accettata');
});

test('tre secondi', () => {
  assert.equal(SECONDI_CONTO, 3);
});

test('la preferenza del conto si ricorda nell\'archivio del browser', () => {
  const dati = new Map();
  const archivio = { getItem: (k) => dati.get(k) ?? null, setItem: (k, v) => dati.set(k, v) };
  assert.equal(leggiPreferenzaConto(archivio), false);
  assert.equal(salvaPreferenzaConto(archivio, true), true);
  assert.equal(leggiPreferenzaConto(archivio), true);
  salvaPreferenzaConto(archivio, false);
  assert.equal(leggiPreferenzaConto(archivio), false);
});

test('senza archivio, o con uno che rifiuta, il conto è spento e la scelta vale per la sessione', () => {
  const ostile = {
    getItem: () => { throw new Error('SecurityError'); },
    setItem: () => { throw new Error('QuotaExceededError'); },
  };
  assert.equal(leggiPreferenzaConto(null), false);
  assert.equal(leggiPreferenzaConto(ostile), false);
  assert.equal(salvaPreferenzaConto(null, true), false);
  assert.equal(salvaPreferenzaConto(ostile, true), false);
});
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `node --test "web/test/*.test.js"`
Expected: FAIL: `SECONDI_CONTO`, `leggiPreferenzaConto`, `salvaPreferenzaConto` non sono esportati (SyntaxError sull'import).

- [ ] **Step 3: scrivi il codice**

In `web/static/stati.js`, la tabella delle transizioni diventa:

```js
const TRANSIZIONI = {
  riposo: { scatta: 'anteprima' },
  anteprima: { scattata: 'revisione', conta: 'conto', negata: 'fotocamera_negata', annulla: 'riposo' },
  conto: { scattata: 'revisione', ferma: 'anteprima', annulla: 'riposo', negata: 'fotocamera_negata' },
  revisione: { rifai: 'anteprima', invia: 'invio' },
  invio: { inviata: 'riposo', fallita: 'errore_invio', respinta: 'riposo' },
  errore_invio: { riprova: 'invio', lascia_perdere: 'riposo' },
  fotocamera_negata: { riprova: 'anteprima', annulla: 'riposo' },
};
```

In `schermata`, subito dopo la riga `if (foto?.stato === 'accettata') return { nome: 'accettata' };`, aggiungi:

```js
  // Il conto alla rovescia si mostra come anteprima con il numero sopra: se fosse
  // una schermata a parte, la fotocamera si spegnerebbe proprio prima dello scatto.
  if (locale.fase === 'conto') return { nome: 'anteprima', conto: true };
```

In fondo al file aggiungi:

```js
// Il conto alla rovescia prima dello scatto (facoltativo, spec §3.3). La
// preferenza vive nel browser di quel dispositivo: il servizio non ne sa nulla.
export const SECONDI_CONTO = 3;
const CHIAVE_CONTO = 'rsm.conto_alla_rovescia';

// `archivio` è localStorage, o null quando il browser non lo concede. Ogni accesso
// può fallire (finestra privata, dati del sito bloccati): allora vale «spento».
export function leggiPreferenzaConto(archivio) {
  try {
    return archivio?.getItem(CHIAVE_CONTO) === '1';
  } catch {
    return false;
  }
}

// Dice se la preferenza è stata salvata. Se no, l'interruttore vale per la
// sessione della pagina.
export function salvaPreferenzaConto(archivio, acceso) {
  if (!archivio) return false;
  try {
    archivio.setItem(CHIAVE_CONTO, acceso ? '1' : '0');
    return true;
  } catch {
    return false;
  }
}
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `node --test "web/test/*.test.js"`
Expected: tutti `ok`, `# fail 0` (i 22 di prima più i 7 nuovi).

- [ ] **Step 5: commit**

```bash
git add web/static/stati.js web/test/stati.test.js
git commit -m "page state: an optional countdown phase and its remembered preference"
```

---

### Task 2: la pagina — il numero, «Ferma», l'interruttore — e le prove in Chrome

**Files:**
- Modify: `web/index.html` (la sezione `data-schermata="anteprima"`)
- Modify: `web/static/stile.css` (in fondo)
- Modify: `web/static/app.js` (import, una variabile, `disegna`, `accendiFotocamera`, `scattaFoto`, funzioni nuove dopo `scattaFoto`, `collega`, l'avvio)
- Modify: `docs/differenze-fra-test-e-realta.md` (una riga)
- Test: `tests/e2e/test_pagina.py`

**Interfaces:**
- Consumes (Task 1): `SECONDI_CONTO`, `leggiPreferenzaConto(archivio)`, `salvaPreferenzaConto(archivio, acceso)`, l'evento `conta`/`ferma`, e `schermata(...).conto`.
- Produces: gli elementi `#numero-conto`, `#ferma-conto`, `#interruttore-conto`, `#etichetta-conto`, che le prove in Chrome usano.

- [ ] **Step 1: scrivi le prove in Chrome**

In fondo a `tests/e2e/test_pagina.py` aggiungi (il file ha già `schermata`, `aspetta` e `import time`):

```python
def _in_anteprima(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert aspetta(lambda: pagina.evaluate("document.getElementById('video').videoWidth") > 0)


def test_il_conto_alla_rovescia_aspetta_tre_secondi_e_scatta(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    inizio = time.monotonic()
    pagina.click("#scatta-foto")
    numero = pagina.locator("#numero-conto")
    numero.wait_for(state="visible")
    assert numero.inner_text() == "3"
    assert pagina.locator("#ferma-conto").is_visible()
    assert not pagina.locator("#scatta-foto").is_visible()
    assert pagina.locator("#interruttore-conto").is_disabled()
    schermata(pagina, "revisione").wait_for(state="visible", timeout=6000)
    assert time.monotonic() - inizio >= 2.5


def test_ferma_riporta_all_anteprima_senza_scattare(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.click("#scatta-foto")
    pagina.locator("#numero-conto").wait_for(state="visible")
    pagina.click("#ferma-conto")
    pagina.locator("#numero-conto").wait_for(state="hidden")
    assert pagina.locator("#scatta-foto").is_visible()
    time.sleep(3.5)  # oltre i tre secondi: il timer fermato non deve scattare
    assert schermata(pagina, "anteprima").is_visible()
    assert not schermata(pagina, "revisione").is_visible()


def test_l_interruttore_si_ricorda_sul_dispositivo(in_rete, pagina):
    _in_anteprima(in_rete, pagina)
    pagina.check("#interruttore-conto")
    pagina.reload()
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#scatta")
    schermata(pagina, "anteprima").wait_for(state="visible")
    assert pagina.locator("#interruttore-conto").is_checked()
```

Senza l'interruttore lo scatto resta immediato: lo prova già `test_scatto_e_invio_fino_alla_foto_ricevuta`, perché ogni prova parte da un browser nuovo, con l'interruttore spento.

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest -m e2e -q`
Expected: le 3 prove nuove FAIL (`#interruttore-conto` non esiste); le altre passano.

- [ ] **Step 3: la pagina e lo stile**

In `web/index.html`, la sezione dell'anteprima diventa:

```html
    <section data-schermata="anteprima" hidden>
      <div class="inquadratura">
        <video id="video" autoplay playsinline muted></video>
        <p id="numero-conto" class="numero-conto" role="timer" aria-live="assertive" hidden></p>
      </div>
      <div class="azioni">
        <button id="scatta-foto" class="primario">Scatta la foto</button>
        <button id="ferma-conto" class="primario" hidden>Ferma</button>
        <button id="annulla">Annulla</button>
      </div>
      <label class="interruttore">
        <input type="checkbox" id="interruttore-conto">
        <span id="etichetta-conto">Conto alla rovescia</span>
      </label>
    </section>
```

In fondo a `web/static/stile.css`:

```css
/* Il numero del conto alla rovescia, sopra l'anteprima. */
.inquadratura { position: relative; }
.numero-conto {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  font-size: 7rem;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 0 1.5rem rgba(0, 0, 0, 0.8);
  pointer-events: none;
}
.interruttore { display: flex; align-items: center; gap: 0.5rem; margin-top: 1rem; color: var(--tenue); }
.interruttore input { width: 1.2rem; height: 1.2rem; }
```

- [ ] **Step 4: il collegamento in `app.js`**

1. L'import da `./stati.js` diventa:

```js
import {
  ETICHETTE_PANNELLO,
  FASE_INIZIALE,
  SECONDI_CONTO,
  base64UrlInByte,
  conTentativi,
  dopo,
  esadecimale,
  esitoApertura,
  esitoDopoConflitto,
  leggiPreferenzaConto,
  msAllaFineDelRinvio,
  salvaPreferenzaConto,
  schermata,
  vistaNotifiche,
} from './stati.js';
```

2. Dopo `let timerRinvio = null;` aggiungi `let timerConto = null;`.

3. In `disegna()`, subito dopo la riga `$('motivo').textContent = …;`, aggiungi:

```js
  const inConto = Boolean(vista.conto);
  $('numero-conto').hidden = !inConto;
  $('scatta-foto').hidden = inConto;
  $('ferma-conto').hidden = !inConto;
  $('interruttore-conto').disabled = inConto;
```

4. Subito prima di `function accendiFotocamera()` aggiungi:

```js
// La fotocamera serve nell'anteprima e durante il conto alla rovescia.
const fotocameraServe = () => locale.fase === 'anteprima' || locale.fase === 'conto';
```

e dentro `accendiFotocamera` sostituisci `if (locale.fase !== 'anteprima') {` con `if (!fotocameraServe()) {`, e `if (locale.fase === 'anteprima') vai('negata');` con `if (fotocameraServe()) vai('negata');`.

5. `scattaFoto` dice se ha scattato: `if (!video.videoWidth) return;` diventa `if (!video.videoWidth) return false;`, il `return;` dopo l'avviso «Non sono riuscito a fare la foto: riprova.» diventa `return false;`, e dopo `vai('scattata');` aggiungi `return true;`.

6. Subito dopo `scattaFoto` aggiungi:

```js
// --- conto alla rovescia (facoltativo). Muto di proposito: il microfono dei
// giocatori è aperto su Discord, e Craig registra.

function archivioLocale() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function fermaTimerConto() {
  clearInterval(timerConto);
  timerConto = null;
}

function premiScatta() {
  if ($('interruttore-conto').checked) avviaConto();
  else scattaFoto();
}

function avviaConto() {
  let resto = SECONDI_CONTO;
  $('numero-conto').textContent = String(resto);
  vai('conta');
  if (locale.fase !== 'conto') return;
  fermaTimerConto();
  timerConto = setInterval(() => {
    if (locale.fase !== 'conto') {
      fermaTimerConto();
      return;
    }
    resto -= 1;
    if (resto > 0) {
      $('numero-conto').textContent = String(resto);
      return;
    }
    fermaTimerConto();
    scattaAlloZero();
  }, 1000);
}

// Allo zero si scatta solo se la fotocamera ha un'immagine: altrimenti si torna
// all'anteprima e lo si dice, senza fingere una foto.
async function scattaAlloZero() {
  if (!$('video').videoWidth) {
    vai('ferma');
    avvisa('La fotocamera non è ancora pronta: riprova.');
    return;
  }
  const riuscita = await scattaFoto();
  if (!riuscita && locale.fase === 'conto') vai('ferma');
}

function fermaConto() {
  fermaTimerConto();
  vai('ferma');
}
```

7. In `collega()`:
   - `$('scatta-foto').addEventListener('click', scattaFoto);` diventa `$('scatta-foto').addEventListener('click', premiScatta);`
   - `$('annulla').addEventListener('click', () => vai('annulla'));` diventa:

```js
  $('annulla').addEventListener('click', () => {
    fermaTimerConto();
    vai('annulla');
  });
  $('ferma-conto').addEventListener('click', fermaConto);
  $('interruttore-conto').addEventListener('change', () => {
    salvaPreferenzaConto(archivioLocale(), $('interruttore-conto').checked);
  });
```

   - il gestore di `visibilitychange` diventa:

```js
  document.addEventListener('visibilitychange', () => {
    // Non si scatta una foto che la persona non sta guardando.
    if (document.visibilityState === 'hidden' && locale.fase === 'conto') fermaConto();
    if (document.visibilityState === 'visible') aggiorna();
  });
```

8. All'avvio, subito dopo `collega();`:

```js
$('etichetta-conto').textContent = `Conto alla rovescia (${SECONDI_CONTO} secondi)`;
$('interruttore-conto').checked = leggiPreferenzaConto(archivioLocale());
```

- [ ] **Step 5: la differenza fra test e realtà**

In `docs/differenze-fra-test-e-realta.md`, aggiungi in fondo alla tabella:

```markdown
| Nel Chrome dei test la pagina è sempre visibile. | Sul telefono la pagina va sullo sfondo a metà conto alla rovescia (una chiamata, un cambio di app): il conto deve fermarsi senza scattare. | A mano, alla prova generale su un telefono. |
```

- [ ] **Step 6: lancia tutto e verifica**

Run: `uv run pytest -m e2e -q && node --test "web/test/*.test.js" && uv run pytest -q && uv run ruff check src tests strumenti`
Expected: e2e 10 passed (le 7 di prima più le 3 nuove); node tutti `ok`; suite veloce invariata e verde; ruff pulito.

- [ ] **Step 7: commit**

```bash
git add web/index.html web/static/stile.css web/static/app.js tests/e2e/test_pagina.py docs/differenze-fra-test-e-realta.md
git commit -m "page: optional 3-second countdown before the shot, silent, remembered"
```
