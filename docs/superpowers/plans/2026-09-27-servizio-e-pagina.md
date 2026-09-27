# Radiant Selfie Machine: il servizio e la pagina — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un servizio sulla macchina di Nextcloud e una pagina web installabile con cui chi siede al tavolo dei Danni Radiosi scatta il selfie per la miniatura quando il master apre il giro, e Alberto lo valida dal bot Telegram.

**Architecture:** Un servizio FastAPI in un container, con lo stato in SQLite e le foto su disco. Le regole del tempo e degli stati sono pure (`regole.py`); `servizio.py` le compone con lo store, Telegram e il push; le rotte HTTP, il bot e i cicli di fondo restano sottili. La pagina è HTML, CSS e JavaScript senza framework né build: il suo cuore è una macchina a stati (`stati.js`) che non tocca il browser e si prova con Node. Tutto ciò che parla con un sistema lento e non serve alla risposta (push, messaggi del bot) gira dopo la risposta.

**Tech Stack:** Python 3.12 con uv, FastAPI, uvicorn, httpx, Pillow, pywebpush; pytest, ruff; Node 25 (`node --test`) per `stati.js`; Playwright con il Chrome installato per le poche prove da capo a fondo; Docker Compose sul server.

**Spec:** `docs/superpowers/specs/2026-09-27-radiant-selfie-machine-design.md`. Le modifiche a `close-the-circle` (§10 della spec) **non** fanno parte di questo piano: avranno un piano proprio, nel repository di `ctc`.

## Global Constraints

- **Italiano** in ogni testo rivolto a una persona (messaggi della pagina, del bot, del push, errori, commenti, docstring) e nei nomi nuovi, come in `close-the-circle`. I messaggi di commit sono in inglese e brevi, e finiscono con la riga `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Python ≥ 3.12**, gestito con `uv`. Dipendenze di esercizio: `fastapi`, `uvicorn[standard]`, `httpx`, `pillow`, `pywebpush` — nient'altro. Dipendenze di sviluppo: `pytest`, `httpx2` (la chiede il `TestClient` di Starlette 1.x), `ruff`, `playwright`. La pagina non ha dipendenze npm.
- **Parametri, dalla §11 della spec:** rinvio di «Salta» 10 minuti (`RSM_RINVIO_MINUTI`); durata di un giro 48 ore; soglia sotto cui «Apri il giro» non riapre 12 ore; polling della pagina 20 secondi; tentativi automatici di invio 3; dimensione massima di una foto 8 MB; cancellazione delle foto 30 giorni dopo la chiusura del giro; ciclo del pianificatore 30 secondi; lunghezza massima di un motivo 200 caratteri; motivi predefiniti «Sfocata», «Troppo buia», «Viso non inquadrato», «Tagliata» → «tagliata (controlla che tutta la testa sia ben visibile nella foto)».
- **Testi fissi:** annuncio nel gruppo «📸 È il momento del selfie per la miniatura!»; pagina e push «Alberto chiede un'altra foto: <motivo>» (senza motivo: «Alberto chiede un'altra foto») e «La tua foto è stata accettata».
- **Ogni messaggio afferma solo ciò che è stato verificato.** «Foto ricevuta» solo quando lo SHA-256 restituito dal servizio coincide con quello calcolato dalla pagina; «Notifiche attivate» solo dopo che il servizio ha salvato l'iscrizione; «annuncio inviato» solo se Telegram ha risposto `ok`. Il guasto tipico di questo genere di progetto è il referto falso, non l'eccezione.
- **Nessun segreto nei log, negli errori o nel repository:** token del bot, chiave VAPID privata, gettoni. Gli errori di rete verso Telegram non riportano il testo dell'eccezione di httpx (può contenere l'URL, e l'URL contiene il token); il logger `httpx` sta a `WARNING`; uvicorn gira con `--no-access-log`. Il gettone nei log di Nginx è l'unica eccezione, accettata dalla spec.
- **Un gettone assente, sconosciuto o con il ruolo sbagliato riceve 404**, come una pagina che non esiste.
- **Il motivo viaggia sempre come testo semplice:** nessun `parse_mode` nelle chiamate a Telegram.
- **La sicura:** finché `RSM_GRUPPO` è vuoto, l'annuncio va nel gruppo di prova (`RSM_GRUPPO_PROVA`), e la risposta a «Apri il giro» lo dice.
- **Date sempre con fuso orario**; nel database stringhe ISO in UTC a larghezza fissa.
- **La suite veloce resta veloce:** niente rete, niente attese vere, niente browser. Le prove da capo a fondo (`-m e2e`) e il piano reale (`-m reale`) sono escluse di default.
- **TDD:** prima il test che fallisce, poi il minimo che lo fa passare.
- **Ruff:** ogni task finisce con `uv run ruff check src tests` pulito. L'ordine degli import (I001) lo sistema `uv run ruff check --fix`; la lunghezza delle righe non è un errore.
- **Ramo:** si lavora su `servizio-e-pagina`, mai direttamente su `main`. Non si fonde senza l'assenso esplicito di Alberto.

## Verificato prima della consegna

Il codice di questo piano è stato estratto ed eseguito così com'è, in una copia usa e getta, il 27/09/2026: 210 test veloci, 18 test della macchina a stati con Node e 3 prove in Chrome con la webcam finta, tutti verdi; gli 8 test del piano reale saltano dicendo quale variabile manca; `uvicorn --factory rsm.principale:costruisci` risponde su `/salute`, il ciclo del bot interroga il vero Telegram, e il token non compare nel log. La verifica ha trovato quattro difetti, già corretti qui: un test senza la fixture `persone`, un `.encode()` che ruff rifiuta, una prova in Chrome bloccata dalla CSP della pagina (il che dimostra che la CSP funziona), e Python non fissato a 3.12.

## Allineamenti alla spec fatti insieme a questo piano

Scrivendo le interfacce sono emersi cinque dettagli che la spec lasciava impliciti. La spec è già stata aggiornata nello stesso commit di questo piano:

1. **Un ruolo a parte per `ctc`** (`ctc`), invece di riusare `admin`: `ctc` scarica e valida ma non scatta, non riceve push e non compare nel pannello né nel confronto col roster.
2. **La versione della foto** compare nell'elenco per `ctc` e va rimandata con l'esito: senza, `ctc` potrebbe accettare una foto che il giocatore ha sostituito dopo che `ctc` l'aveva scaricata.
3. **`GET /api/persone`** per `ctc doctor`, e **`GET /salute`** per il controllo di salute del container.
4. **La pagina sta in `/p/<gettone>/`**, con la barra finale, e il service worker in `/p/<gettone>/sw.js`: così l'ambito del service worker è la pagina personale, e il tocco sulla notifica sa quale pagina aprire senza che il servizio conosca il gettone.
5. **L'invito push non va a chi ha aperto il giro**, e i push hanno un TTL esplicito: 30 minuti per invito e rinvio, 12 ore per l'esito.

## Struttura dei file

| file | responsabilità |
|---|---|
| `pyproject.toml`, `uv.lock`, `.gitignore` | il progetto Python, le dipendenze, la configurazione di pytest e ruff |
| `docs/differenze-fra-test-e-realta.md` | le convinzioni sul mondo vero che i finti mettono per iscritto, e dove si verificano. Si scrive **prima** dei finti |
| `src/rsm/regole.py` | le regole pure: giro, stati della foto, motivi, rinvii, soprannomi |
| `src/rsm/gettoni.py` | gettoni personali e loro impronta |
| `src/rsm/foto.py` | controllo del JPEG, impronta, file su disco |
| `src/rsm/store.py` | SQLite: persone, giri, foto, rinvii, iscrizioni, valori |
| `src/rsm/telegram.py` | client del bot, senza politica |
| `src/rsm/push.py` | invio Web Push e chiave pubblica VAPID |
| `src/rsm/config.py` | configurazione dall'ambiente, motivi |
| `src/rsm/pulsanti.py` | pulsanti del messaggio di validazione e loro codifica |
| `src/rsm/servizio.py` | le operazioni che pagina, bot e `ctc` chiedono |
| `src/rsm/validazione.py` | la politica del bot: tocchi e motivi scritti |
| `src/rsm/cicli.py` | i due cicli di fondo: lettura del bot e pianificatore |
| `src/rsm/app.py` | le rotte HTTP |
| `src/rsm/principale.py` | costruisce il servizio vero dall'ambiente, avvia i cicli |
| `src/rsm/cli.py` | `rsm persona …`, `rsm vapid genera` |
| `web/index.html`, `web/static/stile.css`, `web/static/app.js` | la pagina e il suo collegamento al browser |
| `web/static/stati.js`, `web/test/stati.test.js`, `web/package.json` | la macchina a stati della pagina e i suoi test |
| `web/sw.js` | il service worker: push e tocco sulla notifica |
| `web/static/icona-192.png`, `web/static/icona-512.png`, `strumenti/icone.py` | le icone, e lo script che le disegna |
| `tests/finti.py`, `tests/immagini.py`, `tests/conftest.py` | finti dei sistemi esterni, immagini di prova, fixture |
| `tests/test_*.py` | la suite veloce |
| `tests/e2e/` | poche prove da capo a fondo in Chrome con la webcam finta |
| `tests/reale/` | il piano reale: bot vero, push vero, servizio pubblicato |
| `Dockerfile`, `compose.yaml`, `.dockerignore`, `config.esempio/rsm.env` | il container e la sua configurazione d'esempio |
| `docs/messa-in-produzione.md`, `README.md` | come si mette in produzione, come si sviluppa |

---
### Task 1: lo scheletro, le differenze fra test e realtà, le regole pure

Il progetto nasce qui, insieme all'elenco delle convinzioni sul mondo vero — prima dei finti, come vuole la regola dei due piani di `close-the-circle` — e al modulo che contiene tutte le regole del tempo e degli stati, senza I/O.

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `src/rsm/__init__.py`, `tests/__init__.py`
- Create: `docs/differenze-fra-test-e-realta.md`
- Create: `src/rsm/regole.py`
- Test: `tests/test_regole.py`

**Interfaces:**
- Consumes: niente.
- Produces (`rsm.regole`): costanti `DURATA_GIRO`, `SOGLIA_RIAPERTURA`, `CONSERVAZIONE`, `MOTIVO_MASSIMO = 200`, `IN_ATTESA = "in_attesa"`, `ACCETTATA = "accettata"`, `DA_RIFARE = "da_rifare"`, `GIOCATORE`, `MASTER`, `ADMIN`, `CTC`, `RUOLI`, `CHI_SCATTA`, `CHI_APRE`; eccezione `RegolaViolata`; `@dataclass(frozen=True) Giro(id: int, aperto_alle: datetime, aperto_da: str, chiuso_alle: datetime | None = None, sessione: str | None = None)`; `fine(giro) -> datetime`; `aperto(giro, ora) -> bool`; `@dataclass(frozen=True) Apertura(riusa: Giro | None, chiudi: Giro | None)`; `decidi_apertura(ultimo: Giro | None, ora) -> Apertura`; `stato_dopo_invio(attuale: str | None, ruolo: str) -> str`; `motivo_valido(testo: str) -> str`; `verifica_esito(esito: str, motivo: str | None) -> str | None`; `rinvio_fino_a(ora, minuti) -> datetime`; `rinvio_da_notificare(fino_a, notificato: bool, stato_foto: str | None, ora) -> bool`; `da_cancellare(giro, ora) -> bool`; `soprannome_valido(soprannome) -> str`; `stato_pannello(stato_foto: str | None, rinvio_attivo: bool) -> str`.

- [ ] **Step 1: crea il ramo e lo scheletro del progetto**

```bash
cd ~/git/python/radiant-selfie-machine
git switch -c servizio-e-pagina
mkdir -p src/rsm tests docs
touch src/rsm/__init__.py tests/__init__.py
uv python pin 3.12
```

`uv python pin` scrive `.python-version`: senza, uv sceglie il Python più recente installato (sul Mac di Alberto il 3.14), mentre il container usa il 3.12.

`pyproject.toml`:

```toml
[project]
name = "radiant-selfie-machine"
version = "0.1.0"
description = "I selfie della miniatura dei Danni Radiosi, scattati dalla pagina"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.141,<1",
    "uvicorn[standard]>=0.30,<1",
    "httpx>=0.28,<1",
    "pillow>=12,<13",
    "pywebpush>=2.5,<3",
]

[project.scripts]
rsm = "rsm.cli:main"

[dependency-groups]
dev = ["pytest>=8", "httpx2>=2.13", "ruff>=0.16", "playwright>=1.63"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rsm"]

[tool.pytest.ini_options]
testpaths = ["tests"]
# Esclusi di default: le prove da capo a fondo aprono Chrome, il piano reale
# tocca Telegram, i servizi push e il servizio pubblicato. La suite veloce deve
# restare veloce, altrimenti smette di essere lanciata.
#   uv run pytest -m e2e      le prove in Chrome
#   uv run pytest -m reale    il piano reale (v. tests/reale/)
addopts = "-m 'not reale and not e2e'"
markers = [
    "reale: verifica un sistema esterno vero, non un suo finto (v. tests/reale/)",
    "e2e: prova da capo a fondo in Chrome con la webcam finta",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
# La lunghezza delle righe la cura `ruff format`, non il linter.
ignore = ["E501"]

[tool.ruff.lint.flake8-bugbear]
# Le dipendenze di FastAPI si dichiarano proprio così, nei valori predefiniti.
extend-immutable-calls = ["fastapi.Depends", "fastapi.Body", "fastapi.Header"]
```

`.gitignore`:

```
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
/dati/
/config/
*.pem
```

Poi:

```bash
uv sync
```

Expected: crea `.venv/` e `uv.lock` senza errori.

- [ ] **Step 2: scrivi l'elenco delle differenze fra test e realtà**

`docs/differenze-fra-test-e-realta.md`:

```markdown
# Differenze fra test e realtà

Ogni finto mette per iscritto una convinzione sul mondo vero, e un finto non
può smentire chi l'ha scritto: la conferma con un pallino verde. Questo elenco
dice quali convinzioni stanno nei finti e dove vengono messe alla prova contro
il vero. Si scrive prima dei finti, e si aggiorna ogni volta che il vero ne
smentisce una.

| Nei test | Nella realtà | Dove si verifica |
|---|---|---|
| La webcam è quella finta di Chrome (`--use-fake-device-for-media-stream`): c'è sempre, dà sempre un'immagine, il permesso è già concesso. | La fotocamera può mancare, essere occupata da un'altra applicazione o essere negata. | A mano, alla prova generale. La pagina ha la schermata «fotocamera negata». |
| Il permesso della fotocamera si chiede una volta. | Su iPhone, nella pagina aggiunta alla schermata Home, può essere richiesto a ogni apertura. | A mano, su un iPhone. |
| Il push arriva sempre (`NotificheFinte`). | Il servizio push accetta (201), ma la consegna non è garantita. Su iPhone arriva solo alla pagina aggiunta alla schermata Home (iOS 16.4+); su desktop solo se il browser è in esecuzione. | `tests/reale/test_push_vero.py` verifica che il servizio push accetti la nostra firma; che la notifica compaia lo verifica una persona. |
| `pywebpush.webpush` è chiamato con argomenti che registriamo. | `webpush` modifica `vapid_claims` sul posto (ci scrive l'«aud» del primo servizio push) e ha TTL 0 per default: riusare il dizionario firma per il destinatario sbagliato, e un telefono spento perde la notifica. | `tests/test_push.py` (un dizionario nuovo a ogni invio, TTL esplicito) e `tests/reale/test_push_vero.py`. |
| Telegram risponde subito e con `ok: true` (`TelegramFinto`). | Può fallire o rallentare; rifiuta una chat inesistente e non può scrivere a chi non ha mai mandato /start al bot. | `tests/reale/test_telegram_vero.py`. |
| Il bot legge gli aggiornamenti senza concorrenti. | Due programmi che leggono lo stesso bot si rubano gli aggiornamenti (409 Conflict); con un webhook attivo `getUpdates` non funziona. | `tests/reale/test_telegram_vero.py` controlla che non ci sia un webhook. Il bot del servizio è separato da quello di `ctc`. |
| httpx non scrive log. | Al livello INFO httpx scrive l'URL di ogni richiesta, e l'URL di Telegram contiene il token. | `tests/test_app.py` controlla che `costruisci` alzi il livello del logger `httpx`. |
| Il client parla direttamente col servizio (`TestClient`). | In mezzo c'è Nginx, che per default rifiuta i corpi oltre 1 MB con un suo 413. | `tests/reale/test_servizio_pubblicato.py` manda un corpo da 7,5 MB. |
| Il servizio gira su 127.0.0.1, che per il browser è un contesto sicuro. | Fotocamera, service worker e `crypto.subtle` esigono HTTPS con un certificato valido. | `tests/reale/test_servizio_pubblicato.py`. |
| L'orologio è finto e coincide per tutti. | L'orologio del telefono può essere sbagliato. | La pagina misura il rinvio sull'ora del server (`ora` in `/api/stato`), non sulla propria. |
```

- [ ] **Step 3: scrivi i test delle regole**

`tests/test_regole.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from rsm import regole
from rsm.regole import Giro

T0 = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)


def giro(aperto_alle=T0, chiuso_alle=None):
    return Giro(id=1, aperto_alle=aperto_alle, aperto_da="gio", chiuso_alle=chiuso_alle)


def test_un_giro_resta_aperto_48_ore_esatte():
    g = giro()
    assert regole.aperto(g, T0 + timedelta(hours=48) - timedelta(microseconds=1))
    assert not regole.aperto(g, T0 + timedelta(hours=48))


def test_un_giro_chiuso_prima_della_scadenza_finisce_alla_chiusura():
    g = giro(chiuso_alle=T0 + timedelta(hours=13))
    assert regole.fine(g) == T0 + timedelta(hours=13)
    assert not regole.aperto(g, T0 + timedelta(hours=13))


def test_senza_giri_si_apre_un_giro_nuovo():
    assert regole.decidi_apertura(None, T0) == regole.Apertura(riusa=None, chiudi=None)


def test_sotto_le_12_ore_si_riusa_il_giro_aperto():
    g = giro()
    decisione = regole.decidi_apertura(g, T0 + timedelta(hours=11, minutes=59))
    assert decisione == regole.Apertura(riusa=g, chiudi=None)


def test_dalle_12_ore_si_chiude_il_vecchio_e_se_ne_apre_uno_nuovo():
    g = giro()
    decisione = regole.decidi_apertura(g, T0 + timedelta(hours=12))
    assert decisione == regole.Apertura(riusa=None, chiudi=g)


def test_un_giro_gia_scaduto_non_va_chiuso_di_nuovo():
    decisione = regole.decidi_apertura(giro(), T0 + timedelta(hours=49))
    assert decisione == regole.Apertura(riusa=None, chiudi=None)


@pytest.mark.parametrize("ruolo", ["giocatore", "master"])
@pytest.mark.parametrize("attuale", [None, "in_attesa", "da_rifare"])
def test_la_foto_di_chi_gioca_va_in_attesa(ruolo, attuale):
    assert regole.stato_dopo_invio(attuale, ruolo) == "in_attesa"


def test_la_foto_di_alberto_e_accettata_all_arrivo():
    assert regole.stato_dopo_invio(None, "admin") == "accettata"


def test_una_foto_accettata_e_definitiva():
    with pytest.raises(regole.RegolaViolata, match="definitiva"):
        regole.stato_dopo_invio("accettata", "giocatore")


def test_ctc_non_scatta():
    with pytest.raises(regole.RegolaViolata, match="non scatta"):
        regole.stato_dopo_invio(None, "ctc")


def test_un_esito_sconosciuto_e_rifiutato():
    with pytest.raises(regole.RegolaViolata, match="sconosciuto"):
        regole.verifica_esito("forse", None)


def test_il_motivo_accompagna_solo_la_richiesta_di_un_altra_foto():
    with pytest.raises(regole.RegolaViolata, match="solo la richiesta"):
        regole.verifica_esito("accettata", "sfocata")


def test_il_motivo_si_ripulisce_e_si_restituisce():
    assert regole.verifica_esito("da_rifare", "  troppo buia ") == "troppo buia"
    assert regole.verifica_esito("da_rifare", None) is None
    assert regole.verifica_esito("accettata", None) is None


def test_un_motivo_vuoto_o_troppo_lungo_e_rifiutato():
    with pytest.raises(regole.RegolaViolata, match="vuoto"):
        regole.motivo_valido("   ")
    assert regole.motivo_valido("x" * 200) == "x" * 200
    with pytest.raises(regole.RegolaViolata, match="201 caratteri"):
        regole.motivo_valido("x" * 201)


def test_il_rinvio_dura_i_minuti_richiesti():
    assert regole.rinvio_fino_a(T0, 10) == T0 + timedelta(minutes=10)


def test_un_rinvio_si_notifica_una_volta_sola_e_solo_a_chi_non_ha_una_foto():
    fino_a = T0 + timedelta(minutes=10)
    assert not regole.rinvio_da_notificare(fino_a, False, None, fino_a - timedelta(seconds=1))
    assert regole.rinvio_da_notificare(fino_a, False, None, fino_a)
    assert regole.rinvio_da_notificare(fino_a, False, "da_rifare", fino_a)
    assert not regole.rinvio_da_notificare(fino_a, True, None, fino_a)
    assert not regole.rinvio_da_notificare(fino_a, False, "in_attesa", fino_a)
    assert not regole.rinvio_da_notificare(fino_a, False, "accettata", fino_a)


def test_le_foto_si_cancellano_30_giorni_dopo_la_fine_del_giro():
    g = giro()
    fine = T0 + timedelta(hours=48)
    assert not regole.da_cancellare(g, fine + timedelta(days=30) - timedelta(seconds=1))
    assert regole.da_cancellare(g, fine + timedelta(days=30))


@pytest.mark.parametrize("buono", ["emi", "jean-paul", "a_1", "x" * 32])
def test_soprannomi_ammessi(buono):
    assert regole.soprannome_valido(buono) == buono


@pytest.mark.parametrize("cattivo", ["", "Emi", "../x", "x" * 33, "con spazio", None])
def test_soprannomi_rifiutati(cattivo):
    with pytest.raises(regole.RegolaViolata):
        regole.soprannome_valido(cattivo)


def test_lo_stato_nel_pannello():
    assert regole.stato_pannello(None, False) == "nessuna"
    assert regole.stato_pannello(None, True) == "rinviato"
    assert regole.stato_pannello("in_attesa", True) == "in_attesa"
    assert regole.stato_pannello("da_rifare", False) == "da_rifare"
```

- [ ] **Step 4: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_regole.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.regole'`.

- [ ] **Step 5: scrivi le regole**

`src/rsm/regole.py`:

```python
"""Le regole del giro e delle foto. Niente I/O: solo date, stati e ruoli.

Tutto ciò che dipende dall'ora la riceve come argomento, così i test provano
le 48 ore, le 12 ore e i 30 giorni senza aspettare. Le date hanno sempre il
fuso orario: il servizio lavora in UTC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

DURATA_GIRO = timedelta(hours=48)
SOGLIA_RIAPERTURA = timedelta(hours=12)
CONSERVAZIONE = timedelta(days=30)
MOTIVO_MASSIMO = 200

IN_ATTESA = "in_attesa"
ACCETTATA = "accettata"
DA_RIFARE = "da_rifare"

GIOCATORE = "giocatore"
MASTER = "master"
ADMIN = "admin"
CTC = "ctc"
RUOLI = (GIOCATORE, MASTER, ADMIN, CTC)
CHI_SCATTA = frozenset({GIOCATORE, MASTER, ADMIN})
CHI_APRE = frozenset({MASTER, ADMIN})

_SOPRANNOME = re.compile(r"^[a-z0-9_-]{1,32}$")


class RegolaViolata(Exception):
    """Un'operazione che le regole non ammettono in questo stato."""


@dataclass(frozen=True)
class Giro:
    id: int
    aperto_alle: datetime
    aperto_da: str
    chiuso_alle: datetime | None = None
    sessione: str | None = None


def fine(giro: Giro) -> datetime:
    """Il momento in cui il giro smette di essere aperto."""
    scadenza = giro.aperto_alle + DURATA_GIRO
    if giro.chiuso_alle is not None and giro.chiuso_alle < scadenza:
        return giro.chiuso_alle
    return scadenza


def aperto(giro: Giro, ora: datetime) -> bool:
    return ora < fine(giro)


@dataclass(frozen=True)
class Apertura:
    """Cosa fare quando qualcuno preme «Apri il giro».

    `riusa`: il giro già aperto da restituire così com'è.
    `chiudi`: il giro vecchio da chiudere prima di aprirne uno nuovo.
    Entrambi `None`: si apre un giro nuovo e basta.
    """

    riusa: Giro | None
    chiudi: Giro | None


def decidi_apertura(ultimo: Giro | None, ora: datetime) -> Apertura:
    """Due serate non stanno mai a meno di 12 ore l'una dall'altra: un giro
    aperto da meno di 12 ore è quello di stasera, uno più vecchio no."""
    if ultimo is None or not aperto(ultimo, ora):
        return Apertura(riusa=None, chiudi=None)
    if ora - ultimo.aperto_alle < SOGLIA_RIAPERTURA:
        return Apertura(riusa=ultimo, chiudi=None)
    return Apertura(riusa=None, chiudi=ultimo)


def stato_dopo_invio(attuale: str | None, ruolo: str) -> str:
    """Lo stato di una foto appena ricevuta.

    La foto di Alberto (admin) è accettata all'arrivo: il suo «Invia» è già la
    conferma di chi valida. Una foto accettata è definitiva.
    """
    if ruolo not in CHI_SCATTA:
        raise RegolaViolata(f"il ruolo {ruolo} non scatta")
    if attuale == ACCETTATA:
        raise RegolaViolata("la foto è già stata accettata: è definitiva")
    return ACCETTATA if ruolo == ADMIN else IN_ATTESA


def motivo_valido(testo: str) -> str:
    pulito = testo.strip()
    if not pulito:
        raise RegolaViolata("il motivo è vuoto")
    if len(pulito) > MOTIVO_MASSIMO:
        raise RegolaViolata(
            f"il motivo è lungo {len(pulito)} caratteri: al massimo {MOTIVO_MASSIMO}"
        )
    return pulito


def verifica_esito(esito: str, motivo: str | None) -> str | None:
    """Controlla una decisione su una foto e restituisce il motivo ripulito.

    Che la foto sia davvero in attesa lo controlla chi chiama, perché è un
    conflitto con lo stato (409), non una richiesta sbagliata (400).
    """
    if esito not in (ACCETTATA, DA_RIFARE):
        raise RegolaViolata(f"esito sconosciuto: {esito!r}")
    if motivo is None:
        return None
    if esito != DA_RIFARE:
        raise RegolaViolata("il motivo accompagna solo la richiesta di un'altra foto")
    return motivo_valido(motivo)


def rinvio_fino_a(ora: datetime, minuti: int) -> datetime:
    return ora + timedelta(minutes=minuti)


def rinvio_da_notificare(
    fino_a: datetime, notificato: bool, stato_foto: str | None, ora: datetime
) -> bool:
    """Un rinvio scaduto si notifica una volta sola, e solo a chi non ha già
    una foto in attesa o accettata."""
    return not notificato and fino_a <= ora and stato_foto not in (IN_ATTESA, ACCETTATA)


def da_cancellare(giro: Giro, ora: datetime) -> bool:
    return ora >= fine(giro) + CONSERVAZIONE


def soprannome_valido(soprannome: str) -> str:
    """Lo stesso alfabeto di `validate.nickname` in close-the-circle: il
    soprannome finisce in un nome di file, qui e là."""
    if not isinstance(soprannome, str) or not _SOPRANNOME.fullmatch(soprannome):
        raise RegolaViolata(f"soprannome non valido: {soprannome!r}")
    return soprannome


def stato_pannello(stato_foto: str | None, rinvio_attivo: bool) -> str:
    """Quello che il pannello di master e admin mostra per una persona."""
    if stato_foto is not None:
        return stato_foto
    return "rinviato" if rinvio_attivo else "nessuna"
```

- [ ] **Step 6: lancia i test e verifica che passino**

Run: `uv run pytest tests/test_regole.py -q && uv run ruff check src tests`
Expected: tutti PASS; `All checks passed!`

- [ ] **Step 7: commit**

```bash
git add pyproject.toml uv.lock .python-version .gitignore src tests docs/differenze-fra-test-e-realta.md
git commit -m "scaffold: project, test/reality differences, pure rules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: gettoni e foto

Il gettone è il segreto nel link di ciascuno: nel database ne finisce solo l'impronta. La foto arriva dalla rete e finirà in `Miniatura/`: il controllo è severo, e il salvataggio passa da un file temporaneo, perché la versione della foto la decide il database.

**Files:**
- Create: `src/rsm/gettoni.py`, `src/rsm/foto.py`, `tests/immagini.py`
- Test: `tests/test_gettoni.py`, `tests/test_foto.py`

**Interfaces:**
- Consumes: `regole.soprannome_valido`, `regole.RegolaViolata` (Task 1).
- Produces (`rsm.gettoni`): `genera() -> str`, `impronta(gettone: str) -> str` (SHA-256 esadecimale, 64 caratteri).
- Produces (`rsm.foto`): `MASSIMO = 8 * 1024 * 1024`, `PIXEL_MASSIMI = 50_000_000`; eccezioni `FotoRifiutata(ValueError)` con attributo di classe `codice = 400`, `FotoTroppoGrande(FotoRifiutata)` con `codice = 413`, `FotoNonJpeg(FotoRifiutata)` con `codice = 415`; `valida(dati: bytes) -> None`; `impronta(dati: bytes) -> str`; `percorso(cartella: Path, giro_id: int, soprannome: str, versione: int) -> Path`; `salva_temporaneo(cartella, giro_id, soprannome, dati) -> Path`; `promuovi(temporaneo: Path, cartella, giro_id, soprannome, versione) -> Path`; `leggi(cartella, giro_id, soprannome, versione) -> bytes`; `cancella(cartella, giro_id, soprannome, versione) -> None`; `cancella_giro(cartella, giro_id) -> None`.
- Produces (`tests.immagini`): `jpeg(larghezza=64, altezza=48, colore=(120, 80, 200)) -> bytes`, `png() -> bytes`.

- [ ] **Step 1: scrivi l'aiuto per le immagini di prova e i test**

`tests/immagini.py`:

```python
"""Immagini vere, generate al volo: un finto di JPEG non proverebbe niente."""

from io import BytesIO

from PIL import Image


def jpeg(larghezza: int = 64, altezza: int = 48, colore=(120, 80, 200)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (larghezza, altezza), colore).save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (0, 0, 0)).save(buffer, "PNG")
    return buffer.getvalue()
```

`tests/test_gettoni.py`:

```python
import string

from rsm import gettoni


def test_due_gettoni_sono_diversi_e_lunghi_abbastanza():
    a, b = gettoni.genera(), gettoni.genera()
    assert a != b
    assert len(a) >= 43
    assert set(a) <= set(string.ascii_letters + string.digits + "-_")


def test_l_impronta_e_stabile_e_non_contiene_il_gettone():
    g = gettoni.genera()
    assert gettoni.impronta(g) == gettoni.impronta(g)
    assert len(gettoni.impronta(g)) == 64
    assert g not in gettoni.impronta(g)
```

`tests/test_foto.py`:

```python
import hashlib

import pytest

from rsm import foto, regole
from tests.immagini import jpeg, png


def test_un_jpeg_vero_passa():
    foto.valida(jpeg())


def test_oltre_8_mb_e_troppo_grande():
    with pytest.raises(foto.FotoTroppoGrande) as errore:
        foto.valida(b"\xff\xd8\xff" + b"0" * foto.MASSIMO)
    assert errore.value.codice == 413


def test_un_png_non_e_un_jpeg():
    with pytest.raises(foto.FotoNonJpeg) as errore:
        foto.valida(png())
    assert errore.value.codice == 415


def test_l_intestazione_giusta_non_basta():
    with pytest.raises(foto.FotoNonJpeg, match="non decodificabile"):
        foto.valida(b"\xff\xd8\xff" + b"spazzatura" * 10)


def test_un_jpeg_troncato_non_si_decodifica():
    dati = jpeg(320, 240)
    with pytest.raises(foto.FotoNonJpeg):
        foto.valida(dati[: len(dati) // 2])


def test_troppi_pixel(monkeypatch):
    monkeypatch.setattr(foto, "PIXEL_MASSIMI", 100)
    with pytest.raises(foto.FotoTroppoGrande, match="pixel"):
        foto.valida(jpeg(64, 48))


def test_l_impronta_e_lo_sha256_dei_byte():
    dati = jpeg()
    assert foto.impronta(dati) == hashlib.sha256(dati).hexdigest()


def test_salva_promuovi_e_leggi(tmp_path):
    dati = jpeg()
    temporaneo = foto.salva_temporaneo(tmp_path, 3, "emi", dati)
    assert temporaneo.parent == tmp_path / "3"
    finale = foto.promuovi(temporaneo, tmp_path, 3, "emi", 1)
    assert finale == tmp_path / "3" / "emi-1.jpg"
    assert not temporaneo.exists()
    assert foto.leggi(tmp_path, 3, "emi", 1) == dati


def test_due_temporanei_della_stessa_persona_non_si_pestano(tmp_path):
    a = foto.salva_temporaneo(tmp_path, 3, "emi", b"a")
    b = foto.salva_temporaneo(tmp_path, 3, "emi", b"b")
    assert a != b


def test_cancella_una_versione_e_un_giro(tmp_path):
    temporaneo = foto.salva_temporaneo(tmp_path, 3, "emi", jpeg())
    foto.promuovi(temporaneo, tmp_path, 3, "emi", 1)
    foto.cancella(tmp_path, 3, "emi", 1)
    assert not (tmp_path / "3" / "emi-1.jpg").exists()
    foto.cancella(tmp_path, 3, "emi", 1)  # già cancellata: nessun errore
    foto.cancella_giro(tmp_path, 3)
    assert not (tmp_path / "3").exists()
    foto.cancella_giro(tmp_path, 3)  # già cancellato: nessun errore


def test_il_soprannome_si_valida_anche_qui(tmp_path):
    with pytest.raises(regole.RegolaViolata):
        foto.percorso(tmp_path, 1, "../fuori", 1)
    with pytest.raises(regole.RegolaViolata):
        foto.salva_temporaneo(tmp_path, 1, "../fuori", b"x")
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_gettoni.py tests/test_foto.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.gettoni'` (e `rsm.foto`).

- [ ] **Step 3: scrivi i due moduli**

`src/rsm/gettoni.py`:

```python
"""I gettoni personali: il segreto che sta nel link di ciascuno.

Nel database finisce solo l'impronta: chi legge il database non può
ricostruire i link.
"""

from __future__ import annotations

import hashlib
import secrets


def genera() -> str:
    return secrets.token_urlsafe(32)


def impronta(gettone: str) -> str:
    return hashlib.sha256(gettone.encode("utf-8")).hexdigest()
```

`src/rsm/foto.py`:

```python
"""Le foto ricevute: controllo, impronta, file su disco.

Il controllo è severo di proposito: la foto arriva dalla rete e finirà in
`Miniatura/` passando per `ctc`. Solo JPEG, al massimo 8 MB, e solo se Pillow
riesce davvero a decodificarla: l'intestazione giusta non basta.

Il file definitivo porta la versione della foto, che decide il database. Per
questo si scrive prima un temporaneo, e lo si promuove quando la versione è
nota: una foto rifiutata dal database non lascia mai un file definitivo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from . import regole

MASSIMO = 8 * 1024 * 1024
PIXEL_MASSIMI = 50_000_000
_INIZIO_JPEG = b"\xff\xd8\xff"


class FotoRifiutata(ValueError):
    codice = 400


class FotoTroppoGrande(FotoRifiutata):
    codice = 413


class FotoNonJpeg(FotoRifiutata):
    codice = 415


def valida(dati: bytes) -> None:
    if len(dati) > MASSIMO:
        raise FotoTroppoGrande(f"la foto pesa {len(dati)} byte: al massimo {MASSIMO}")
    if not dati.startswith(_INIZIO_JPEG):
        raise FotoNonJpeg("non è un JPEG")
    try:
        with Image.open(BytesIO(dati)) as immagine:
            if immagine.format != "JPEG":
                raise FotoNonJpeg("non è un JPEG")
            larghezza, altezza = immagine.size
            if larghezza * altezza > PIXEL_MASSIMI:
                raise FotoTroppoGrande(f"la foto ha {larghezza}×{altezza} pixel: troppi")
            immagine.load()
    except FotoRifiutata:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as e:
        raise FotoNonJpeg("JPEG non decodificabile") from e


def impronta(dati: bytes) -> str:
    return hashlib.sha256(dati).hexdigest()


def _cartella_giro(cartella: Path, giro_id: int) -> Path:
    return cartella / str(int(giro_id))


def percorso(cartella: Path, giro_id: int, soprannome: str, versione: int) -> Path:
    regole.soprannome_valido(soprannome)
    return _cartella_giro(cartella, giro_id) / f"{soprannome}-{int(versione)}.jpg"


def salva_temporaneo(cartella: Path, giro_id: int, soprannome: str, dati: bytes) -> Path:
    regole.soprannome_valido(soprannome)
    destinazione = _cartella_giro(cartella, giro_id)
    destinazione.mkdir(parents=True, exist_ok=True)
    temporaneo = destinazione / f".{soprannome}-{uuid.uuid4().hex}.tmp"
    temporaneo.write_bytes(dati)
    return temporaneo


def promuovi(
    temporaneo: Path, cartella: Path, giro_id: int, soprannome: str, versione: int
) -> Path:
    finale = percorso(cartella, giro_id, soprannome, versione)
    os.replace(temporaneo, finale)
    return finale


def leggi(cartella: Path, giro_id: int, soprannome: str, versione: int) -> bytes:
    return percorso(cartella, giro_id, soprannome, versione).read_bytes()


def cancella(cartella: Path, giro_id: int, soprannome: str, versione: int) -> None:
    percorso(cartella, giro_id, soprannome, versione).unlink(missing_ok=True)


def cancella_giro(cartella: Path, giro_id: int) -> None:
    destinazione = _cartella_giro(cartella, giro_id)
    if destinazione.is_dir():
        shutil.rmtree(destinazione)
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest tests/test_gettoni.py tests/test_foto.py -q && uv run ruff check src tests`
Expected: tutti PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/gettoni.py src/rsm/foto.py tests/immagini.py tests/test_gettoni.py tests/test_foto.py
git commit -m "tokens and photo validation/storage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: lo store SQLite

Tutto lo stato del servizio. Una connessione per operazione, perché FastAPI esegue le rotte sincrone in un pool di thread. Due operazioni hanno la guardia nel SQL e non solo nel Python: la sostituzione di una foto (mai sopra una foto accettata) e la decisione (solo sulla versione vista e solo se ancora in attesa). Così una corsa fra due richieste non può produrre uno stato che le regole vietano.

**Files:**
- Create: `src/rsm/store.py`, `tests/conftest.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `regole.Giro` (Task 1).
- Produces (`rsm.store`): dataclass immutabili `Persona(soprannome, ruolo)`, `Foto(giro_id, soprannome, versione, stato, sha256, byte, ricevuta_alle: datetime, motivo: str | None, messaggio_bot: int | None, attesa_motivo: int | None)`, `Rinvio(giro_id, soprannome, fino_a: datetime, notificato: bool)`, `Iscrizione(endpoint, soprannome, p256dh, auth)`; classe `Store(percorso)` con: `crea_schema()`; `aggiungi_persona(soprannome, ruolo, impronta)` (solleva `sqlite3.IntegrityError` se esiste), `sostituisci_gettone(soprannome, impronta) -> bool`, `rimuovi_persona(soprannome) -> bool`, `persona_da_impronta(impronta) -> Persona | None`, `persone() -> list[Persona]`; `ultimo_giro() -> Giro | None`, `giro(giro_id) -> Giro | None`, `crea_giro(aperto_alle, aperto_da) -> Giro`, `chiudi_giro(giro_id, alle)`, `giri_dal(dal) -> list[Giro]`, `lega(giro_id, sessione) -> bool`, `giri_con_foto() -> list[Giro]`; `foto(giro_id, soprannome) -> Foto | None`, `foto_del_giro(giro_id) -> list[Foto]`, `salva_foto(giro_id, soprannome, stato, sha256, byte, alle) -> Foto | None`, `imposta_messaggio_bot(giro_id, soprannome, versione, messaggio) -> bool`, `decidi(giro_id, soprannome, versione, stato, motivo) -> bool`, `imposta_attesa_motivo(giro_id, soprannome, versione, messaggio) -> bool`, `foto_in_attesa_di_motivo(messaggio) -> Foto | None`, `cancella_foto_giro(giro_id)`; `imposta_rinvio(giro_id, soprannome, fino_a)`, `rinvio(giro_id, soprannome) -> Rinvio | None`, `rinvii_scaduti(ora) -> list[Rinvio]`, `segna_rinvio_notificato(giro_id, soprannome)`; `aggiungi_iscrizione(iscrizione)`, `togli_iscrizione(endpoint, soprannome: str | None = None)`, `iscrizioni_di(soprannome) -> list[Iscrizione]`; `leggi_valore(chiave) -> str | None`, `scrivi_valore(chiave, valore)`.
- Produces (`tests/conftest.py`): fixture `store` (uno `Store` vuoto in `tmp_path / "rsm.sqlite"`, schema creato).

- [ ] **Step 1: scrivi la fixture e i test**

`tests/conftest.py`:

```python
import pytest

from rsm.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "rsm.sqlite")
    s.crea_schema()
    return s
```

`tests/test_store.py`:

```python
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from rsm.store import Iscrizione, Persona, Store

T0 = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)


def test_lo_schema_si_puo_creare_due_volte(store):
    store.crea_schema()


def test_persone_per_impronta_e_in_ordine(store):
    store.aggiungi_persona("gio", "master", "h-gio")
    store.aggiungi_persona("emi", "giocatore", "h-emi")
    assert store.persona_da_impronta("h-gio") == Persona("gio", "master")
    assert store.persona_da_impronta("sconosciuta") is None
    assert [p.soprannome for p in store.persone()] == ["emi", "gio"]


def test_una_persona_non_si_aggiunge_due_volte(store):
    store.aggiungi_persona("emi", "giocatore", "h1")
    with pytest.raises(sqlite3.IntegrityError):
        store.aggiungi_persona("emi", "giocatore", "h2")


def test_sostituire_il_gettone_annulla_il_vecchio(store):
    store.aggiungi_persona("emi", "giocatore", "vecchio")
    assert store.sostituisci_gettone("emi", "nuovo")
    assert store.persona_da_impronta("vecchio") is None
    assert store.persona_da_impronta("nuovo") == Persona("emi", "giocatore")
    assert not store.sostituisci_gettone("nessuno", "x")


def test_rimuovere_una_persona_toglie_anche_le_sue_iscrizioni(store):
    store.aggiungi_persona("prova", "giocatore", "h")
    store.aggiungi_iscrizione(Iscrizione("https://push/1", "prova", "p", "a"))
    assert store.rimuovi_persona("prova")
    assert store.persona_da_impronta("h") is None
    assert store.iscrizioni_di("prova") == []
    assert not store.rimuovi_persona("prova")


def test_un_ruolo_sconosciuto_e_rifiutato_dal_database(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.aggiungi_persona("x", "imperatore", "h")


def test_giri_crea_leggi_chiudi(store):
    assert store.ultimo_giro() is None
    g1 = store.crea_giro(T0, "gio")
    g2 = store.crea_giro(T0 + timedelta(days=3), "abe")
    assert store.ultimo_giro() == g2
    assert store.giro(g1.id) == g1
    assert store.giro(999) is None
    store.chiudi_giro(g1.id, T0 + timedelta(hours=1))
    store.chiudi_giro(g1.id, T0 + timedelta(hours=5))  # una chiusura non si sposta
    assert store.giro(g1.id).chiuso_alle == T0 + timedelta(hours=1)


def test_le_date_non_perdono_il_fuso_e_rifiutano_le_ingenue(store):
    g = store.crea_giro(T0, "gio")
    assert store.giro(g.id).aperto_alle.tzinfo is not None
    with pytest.raises(ValueError, match="fuso"):
        store.crea_giro(datetime(2026, 10, 4, 19, 30), "gio")


def test_giri_dal_comprende_il_limite(store):
    prima = store.crea_giro(T0 - timedelta(microseconds=1), "gio")
    esatto = store.crea_giro(T0, "gio")
    dopo = store.crea_giro(T0 + timedelta(hours=1), "gio")
    assert [g.id for g in store.giri_dal(T0)] == [esatto.id, dopo.id]
    assert prima.id not in [g.id for g in store.giri_dal(T0)]


def test_legare_un_giro_riesce_una_volta_sola(store):
    g = store.crea_giro(T0, "gio")
    assert store.lega(g.id, "2026-10-04")
    assert not store.lega(g.id, "2026-10-05")
    assert store.giro(g.id).sessione == "2026-10-04"


def test_salva_foto_crea_poi_sostituisce_e_azzera_motivo_e_messaggi(store):
    g = store.crea_giro(T0, "gio")
    prima = store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    assert prima.versione == 1 and prima.stato == "in_attesa"
    store.imposta_messaggio_bot(g.id, "emi", 1, 555)
    store.decidi(g.id, "emi", 1, "da_rifare", "sfocata")
    seconda = store.salva_foto(g.id, "emi", "in_attesa", "sha2", 20, T0 + timedelta(minutes=1))
    assert seconda.versione == 2
    assert (seconda.sha256, seconda.byte, seconda.motivo, seconda.messaggio_bot) == (
        "sha2",
        20,
        None,
        None,
    )


def test_una_foto_accettata_non_si_sostituisce(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "abe", "accettata", "sha1", 10, T0)
    assert store.salva_foto(g.id, "abe", "in_attesa", "sha2", 20, T0) is None
    assert store.foto(g.id, "abe").sha256 == "sha1"


def test_decidere_vale_solo_per_la_versione_vista_e_in_attesa(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    store.salva_foto(g.id, "emi", "in_attesa", "sha2", 10, T0)
    assert not store.decidi(g.id, "emi", 1, "accettata", None)
    assert store.decidi(g.id, "emi", 2, "accettata", None)
    assert not store.decidi(g.id, "emi", 2, "da_rifare", None)
    assert store.foto(g.id, "emi").stato == "accettata"


def test_l_attesa_del_motivo(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    assert store.imposta_attesa_motivo(g.id, "emi", 1, 777)
    assert store.foto_in_attesa_di_motivo(777).soprannome == "emi"
    assert store.foto_in_attesa_di_motivo(778) is None
    store.decidi(g.id, "emi", 1, "da_rifare", "occhi chiusi")
    assert store.foto_in_attesa_di_motivo(777) is None
    assert not store.imposta_attesa_motivo(g.id, "emi", 1, 779)


def test_una_foto_nuova_annulla_l_attesa_del_motivo(store):
    g = store.crea_giro(T0, "gio")
    store.salva_foto(g.id, "emi", "in_attesa", "sha1", 10, T0)
    store.imposta_attesa_motivo(g.id, "emi", 1, 777)
    store.salva_foto(g.id, "emi", "in_attesa", "sha2", 10, T0)
    assert store.foto_in_attesa_di_motivo(777) is None


def test_foto_del_giro_giri_con_foto_e_cancellazione(store):
    g1 = store.crea_giro(T0, "gio")
    g2 = store.crea_giro(T0 + timedelta(days=3), "gio")
    store.salva_foto(g1.id, "sem", "in_attesa", "a", 1, T0)
    store.salva_foto(g1.id, "emi", "in_attesa", "b", 1, T0)
    assert [f.soprannome for f in store.foto_del_giro(g1.id)] == ["emi", "sem"]
    assert [g.id for g in store.giri_con_foto()] == [g1.id]
    store.cancella_foto_giro(g1.id)
    assert store.foto_del_giro(g1.id) == []
    assert store.giri_con_foto() == []
    assert store.giro(g2.id) is not None


def test_rinvii_scadenza_e_notifica(store):
    g = store.crea_giro(T0, "gio")
    store.imposta_rinvio(g.id, "emi", T0 + timedelta(minutes=10))
    assert store.rinvii_scaduti(T0 + timedelta(minutes=9)) == []
    scaduti = store.rinvii_scaduti(T0 + timedelta(minutes=10))
    assert [(r.soprannome, r.notificato) for r in scaduti] == [("emi", False)]
    store.segna_rinvio_notificato(g.id, "emi")
    assert store.rinvii_scaduti(T0 + timedelta(hours=1)) == []
    store.imposta_rinvio(g.id, "emi", T0 + timedelta(minutes=30))  # un nuovo «Salta»
    assert store.rinvio(g.id, "emi").notificato is False


def test_iscrizioni(store):
    store.aggiungi_iscrizione(Iscrizione("https://push/1", "emi", "p1", "a1"))
    store.aggiungi_iscrizione(Iscrizione("https://push/1", "sem", "p2", "a2"))
    assert store.iscrizioni_di("emi") == []
    assert store.iscrizioni_di("sem") == [Iscrizione("https://push/1", "sem", "p2", "a2")]
    store.togli_iscrizione("https://push/1", soprannome="emi")  # non è sua
    assert len(store.iscrizioni_di("sem")) == 1
    store.togli_iscrizione("https://push/1")
    assert store.iscrizioni_di("sem") == []


def test_valori(store):
    assert store.leggi_valore("offset") is None
    store.scrivi_valore("offset", "5")
    store.scrivi_valore("offset", "6")
    assert store.leggi_valore("offset") == "6"


def test_un_altro_store_sullo_stesso_file_vede_i_dati(store, tmp_path):
    store.aggiungi_persona("emi", "giocatore", "h")
    assert Store(tmp_path / "rsm.sqlite").persona_da_impronta("h") == Persona("emi", "giocatore")
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_store.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.store'`.

- [ ] **Step 3: scrivi lo store**

`src/rsm/store.py`:

```python
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

    def chiudi_giro(self, giro_id: int, alle: datetime) -> None:
        with self._connessione() as c:
            c.execute(
                "UPDATE giri SET chiuso_alle = ? WHERE id = ? AND chiuso_alle IS NULL",
                (_iso(alle), giro_id),
            )

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

    def segna_rinvio_notificato(self, giro_id: int, soprannome: str) -> None:
        with self._connessione() as c:
            c.execute(
                "UPDATE rinvii SET notificato = 1 WHERE giro_id = ? AND soprannome = ?",
                (giro_id, soprannome),
            )

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
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest tests/test_store.py -q && uv run ruff check src tests`
Expected: tutti PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/store.py tests/conftest.py tests/test_store.py
git commit -m "SQLite store with SQL-level guards on photo replace and decide

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: il client del bot Telegram

Un client sottile sull'API HTTP di Telegram, con httpx. Nessuna politica: chi decide cosa scrivere e quando sta in `servizio.py` e `validazione.py`. Il token sta nell'URL di ogni chiamata: gli errori non devono mai riportarlo.

**Files:**
- Create: `src/rsm/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Consumes: niente dai task precedenti.
- Produces (`rsm.telegram`): `Pulsanti = list[list[tuple[str, str]]]` (righe di coppie testo/callback_data); eccezione `TelegramError(RuntimeError)`; classe `BotTelegram(token: str, http: httpx.Client | None = None)` con `scrivi(chat_id: int, testo: str) -> int` (id del messaggio), `manda_foto(chat_id: int, dati: bytes, didascalia: str, pulsanti: Pulsanti) -> int`, `modifica_didascalia(chat_id: int, messaggio: int, testo: str, pulsanti: Pulsanti | None = None) -> None` (con `None` toglie i pulsanti), `chiedi_risposta(chat_id: int, testo: str) -> int`, `rispondi_tocco(tocco_id: str, testo: str) -> None`, `aggiornamenti(offset: int | None, attesa: int) -> list[dict]`, `webhook_attivo() -> bool`.

- [ ] **Step 1: scrivi i test**

`tests/test_telegram.py`:

```python
import json

import httpx
import pytest

from rsm.telegram import BotTelegram, TelegramError
from tests.immagini import jpeg

TOKEN = "123:SEGRETO"


def bot_con(gestore):
    return BotTelegram(TOKEN, http=httpx.Client(transport=httpx.MockTransport(gestore)))


def ok(risultato):
    return httpx.Response(200, json={"ok": True, "result": risultato})


def registra(risultato):
    viste = []

    def gestore(richiesta):
        viste.append(richiesta)
        return ok(risultato)

    return viste, gestore


def test_scrivi_manda_testo_semplice_e_restituisce_l_id():
    viste, gestore = registra({"message_id": 42})
    assert bot_con(gestore).scrivi(-100, "ciao *non* markdown") == 42
    assert viste[0].url.path == f"/bot{TOKEN}/sendMessage"
    # niente parse_mode: il motivo scritto da Alberto è testo semplice
    assert json.loads(viste[0].content) == {"chat_id": -100, "text": "ciao *non* markdown"}


def test_manda_foto_in_multipart_con_i_pulsanti():
    viste, gestore = registra({"message_id": 7})
    dati = jpeg()
    pulsanti = [[("✅ Va bene", "v|1|emi|1|ok")], [("Sfocata", "v|1|emi|1|m0")]]
    assert bot_con(gestore).manda_foto(123456789, dati, "Selfie di emi", pulsanti) == 7
    corpo = viste[0].content
    assert viste[0].url.path.endswith("/sendPhoto")
    assert dati in corpo
    assert b'filename="selfie.jpg"' in corpo
    assert b'"callback_data": "v|1|emi|1|ok"' in corpo
    assert b"Selfie di emi" in corpo


def test_modifica_didascalia_senza_pulsanti_li_toglie():
    viste, gestore = registra(True)
    bot_con(gestore).modifica_didascalia(123456789, 7, "✅ accettata")
    corpo = json.loads(viste[0].content)
    assert corpo == {
        "chat_id": 123456789,
        "message_id": 7,
        "caption": "✅ accettata",
        "reply_markup": {"inline_keyboard": []},
    }


def test_modifica_didascalia_con_pulsanti_li_tiene():
    viste, gestore = registra(True)
    bot_con(gestore).modifica_didascalia(1, 7, "attendo", [[("✅ Va bene", "v|1|emi|1|ok")]])
    tastiera = json.loads(viste[0].content)["reply_markup"]["inline_keyboard"]
    assert tastiera == [[{"text": "✅ Va bene", "callback_data": "v|1|emi|1|ok"}]]


def test_chiedi_risposta_usa_force_reply():
    viste, gestore = registra({"message_id": 900})
    assert bot_con(gestore).chiedi_risposta(1, "Scrivi il motivo per emi") == 900
    corpo = json.loads(viste[0].content)
    assert corpo["reply_markup"]["force_reply"] is True


def test_rispondi_tocco_accorcia_a_200_caratteri():
    viste, gestore = registra(True)
    bot_con(gestore).rispondi_tocco("t1", "x" * 250)
    assert json.loads(viste[0].content) == {"callback_query_id": "t1", "text": "x" * 200}


def test_aggiornamenti_passa_offset_e_attesa():
    viste, gestore = registra([{"update_id": 5}])
    bot = bot_con(gestore)
    assert bot.aggiornamenti(7, 25) == [{"update_id": 5}]
    assert json.loads(viste[0].content) == {
        "timeout": 25,
        "allowed_updates": ["message", "callback_query"],
        "offset": 7,
    }
    bot.aggiornamenti(None, 0)
    assert "offset" not in json.loads(viste[1].content)


def test_webhook_attivo():
    assert bot_con(lambda r: ok({"url": ""})).webhook_attivo() is False
    assert bot_con(lambda r: ok({"url": "https://altrove"})).webhook_attivo() is True


def test_un_rifiuto_dell_api_diventa_telegram_error():
    def gestore(richiesta):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(TelegramError, match="sendMessage: Bad Request: chat not found"):
        bot_con(gestore).scrivi(1, "x")


def test_un_errore_di_rete_non_rivela_il_token():
    def gestore(richiesta):
        raise httpx.ConnectError(f"impossibile raggiungere {richiesta.url}", request=richiesta)

    with pytest.raises(TelegramError) as errore:
        bot_con(gestore).scrivi(1, "x")
    assert "SEGRETO" not in str(errore.value)
    assert errore.value.__cause__ is None
    assert errore.value.__suppress_context__


def test_una_risposta_non_json():
    with pytest.raises(TelegramError, match="HTTP 502"):
        bot_con(lambda r: httpx.Response(502, text="Bad gateway")).scrivi(1, "x")
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_telegram.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.telegram'`.

- [ ] **Step 3: scrivi il client**

`src/rsm/telegram.py`:

```python
"""Il client del bot Telegram del servizio. Nessuna politica: chiama l'API e
restituisce quello che serve.

Il token sta nell'URL di ogni chiamata. Per questo gli errori non riportano mai
il testo delle eccezioni di httpx, che può contenere l'URL, e non le
incatenano (`from None`): un `log.exception` le stamperebbe. Per lo stesso
motivo `principale.py` alza il livello del logger `httpx`, che al livello INFO
scriverebbe ogni URL, token compreso.

Nessuna chiamata usa `parse_mode`: i testi, motivi compresi, sono semplici.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

Pulsanti = list[list[tuple[str, str]]]


class TelegramError(RuntimeError):
    """Una chiamata all'API di Telegram non è andata a buon fine."""


def _tastiera(pulsanti: Pulsanti) -> dict:
    return {
        "inline_keyboard": [
            [{"text": testo, "callback_data": dati} for testo, dati in riga] for riga in pulsanti
        ]
    }


class BotTelegram:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._http = http or httpx.Client(timeout=httpx.Timeout(10.0))

    def _chiama(
        self,
        metodo: str,
        *,
        corpo: dict | None = None,
        campi: dict | None = None,
        file: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        argomenti: dict[str, Any] = {}
        if corpo is not None:
            argomenti["json"] = corpo
        if campi is not None:
            argomenti["data"] = campi
        if file is not None:
            argomenti["files"] = file
        if timeout is not None:
            argomenti["timeout"] = timeout
        try:
            risposta = self._http.post(self._base + metodo, **argomenti)
        except httpx.HTTPError as e:
            raise TelegramError(f"{metodo}: errore di rete ({type(e).__name__})") from None
        try:
            contenuto = risposta.json()
        except ValueError:
            raise TelegramError(
                f"{metodo}: risposta non JSON (HTTP {risposta.status_code})"
            ) from None
        if not contenuto.get("ok"):
            descrizione = contenuto.get("description", "errore senza descrizione")
            raise TelegramError(f"{metodo}: {descrizione}")
        return contenuto["result"]

    def scrivi(self, chat_id: int, testo: str) -> int:
        risultato = self._chiama("sendMessage", corpo={"chat_id": chat_id, "text": testo})
        return risultato["message_id"]

    def manda_foto(self, chat_id: int, dati: bytes, didascalia: str, pulsanti: Pulsanti) -> int:
        risultato = self._chiama(
            "sendPhoto",
            campi={
                "chat_id": str(chat_id),
                "caption": didascalia,
                "reply_markup": json.dumps(_tastiera(pulsanti)),
            },
            file={"photo": ("selfie.jpg", dati, "image/jpeg")},
            timeout=30.0,
        )
        return risultato["message_id"]

    def modifica_didascalia(
        self, chat_id: int, messaggio: int, testo: str, pulsanti: Pulsanti | None = None
    ) -> None:
        self._chiama(
            "editMessageCaption",
            corpo={
                "chat_id": chat_id,
                "message_id": messaggio,
                "caption": testo,
                "reply_markup": _tastiera(pulsanti or []),
            },
        )

    def chiedi_risposta(self, chat_id: int, testo: str) -> int:
        risultato = self._chiama(
            "sendMessage",
            corpo={
                "chat_id": chat_id,
                "text": testo,
                "reply_markup": {"force_reply": True, "input_field_placeholder": "Il motivo"},
            },
        )
        return risultato["message_id"]

    def rispondi_tocco(self, tocco_id: str, testo: str) -> None:
        self._chiama(
            "answerCallbackQuery", corpo={"callback_query_id": tocco_id, "text": testo[:200]}
        )

    def aggiornamenti(self, offset: int | None, attesa: int) -> list[dict]:
        corpo: dict[str, Any] = {"timeout": attesa, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            corpo["offset"] = offset
        return self._chiama("getUpdates", corpo=corpo, timeout=attesa + 10.0)

    def webhook_attivo(self) -> bool:
        return bool(self._chiama("getWebhookInfo").get("url"))
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest tests/test_telegram.py -q && uv run ruff check src tests`
Expected: tutti PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/telegram.py tests/test_telegram.py
git commit -m "Telegram bot client that never leaks the token

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: le notifiche Web Push

L'invio vero passa da `pywebpush`, con due trappole verificate sulla libreria (v. `docs/differenze-fra-test-e-realta.md`): `webpush` scrive dentro `vapid_claims` e ha TTL 0 per default. Un invio fallito non fa mai fallire l'operazione che l'ha causato.

**Files:**
- Create: `src/rsm/push.py`
- Test: `tests/test_push.py`

**Interfaces:**
- Consumes: `Store.iscrizioni_di`, `Store.togli_iscrizione`, `Store.aggiungi_iscrizione`, `Iscrizione` (Task 3).
- Produces (`rsm.push`): `chiave_pubblica(vapid: Vapid01) -> str` (punto non compresso in base64url senza padding, 87 caratteri); classe `Notificatore(store: Store, vapid: Vapid01, contatto: str, invia=pywebpush.webpush)` con `a_persona(soprannome: str, titolo: str, testo: str, *, ttl: int) -> int` (quanti invii il servizio push ha accettato). Il carico utile è il JSON `{"titolo": …, "testo": …}`, che `web/sw.js` (Task 15) legge.

- [ ] **Step 1: scrivi i test**

`tests/test_push.py`:

```python
import base64
import json

import pytest
import requests
from py_vapid import Vapid
from pywebpush import WebPushException

from rsm.push import Notificatore, chiave_pubblica
from rsm.store import Iscrizione


class Risposta:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""
        self.headers = {}


@pytest.fixture
def vapid():
    chiave = Vapid()
    chiave.generate_keys()
    return chiave


@pytest.fixture
def con_iscrizioni(store):
    store.aggiungi_iscrizione(Iscrizione("https://fcm.googleapis.com/fcm/send/a", "emi", "p1", "a1"))
    store.aggiungi_iscrizione(Iscrizione("https://updates.push.services.mozilla.com/b", "emi", "p2", "a2"))
    store.aggiungi_iscrizione(Iscrizione("https://fcm.googleapis.com/fcm/send/c", "gio", "p3", "a3"))
    return store


def test_manda_a_ogni_iscrizione_della_persona(con_iscrizioni, vapid):
    chiamate = []
    n = Notificatore(con_iscrizioni, vapid, "mailto:prova@example.org", invia=lambda **kw: chiamate.append(kw))
    assert n.a_persona("emi", "📸 Selfie", "È il momento del selfie!", ttl=1800) == 2
    assert [c["subscription_info"]["endpoint"] for c in chiamate] == [
        "https://fcm.googleapis.com/fcm/send/a",
        "https://updates.push.services.mozilla.com/b",
    ]
    assert chiamate[0]["subscription_info"]["keys"] == {"p256dh": "p1", "auth": "a1"}
    assert all(c["ttl"] == 1800 for c in chiamate)
    assert all(c["vapid_private_key"] is vapid for c in chiamate)
    assert json.loads(chiamate[0]["data"]) == {"titolo": "📸 Selfie", "testo": "È il momento del selfie!"}


def test_i_claims_sono_nuovi_a_ogni_invio(con_iscrizioni, vapid):
    """webpush scrive l'«aud» del primo servizio push dentro vapid_claims: se il
    dizionario fosse lo stesso, il secondo invio firmerebbe per Google una
    richiesta destinata a Mozilla, e Mozilla risponderebbe 403."""
    visti = []

    def invia_che_modifica(**kw):
        visti.append(dict(kw["vapid_claims"]))
        kw["vapid_claims"]["aud"] = kw["subscription_info"]["endpoint"]

    Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia_che_modifica).a_persona(
        "emi", "t", "x", ttl=60
    )
    assert visti == [{"sub": "mailto:a@b.c"}, {"sub": "mailto:a@b.c"}]


@pytest.mark.parametrize("stato", [404, 410])
def test_un_iscrizione_scaduta_viene_tolta(con_iscrizioni, vapid, stato):
    def invia(**kw):
        raise WebPushException("scaduta", response=Risposta(stato))

    assert Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia).a_persona("gio", "t", "x", ttl=60) == 0
    assert con_iscrizioni.iscrizioni_di("gio") == []


def test_un_altro_rifiuto_non_toglie_l_iscrizione(con_iscrizioni, vapid):
    def invia(**kw):
        raise WebPushException("errore", response=Risposta(500))

    assert Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia).a_persona("gio", "t", "x", ttl=60) == 0
    assert len(con_iscrizioni.iscrizioni_di("gio")) == 1


def test_un_errore_di_rete_non_esplode(con_iscrizioni, vapid):
    def invia(**kw):
        raise requests.ConnectionError("rete giù")

    assert Notificatore(con_iscrizioni, vapid, "mailto:a@b.c", invia=invia).a_persona("gio", "t", "x", ttl=60) == 0


def test_senza_iscrizioni_non_si_manda_niente(store, vapid):
    chiamate = []
    n = Notificatore(store, vapid, "mailto:a@b.c", invia=lambda **kw: chiamate.append(kw))
    assert n.a_persona("nessuno", "t", "x", ttl=60) == 0
    assert chiamate == []


def test_la_chiave_pubblica_e_un_punto_non_compresso(vapid):
    chiave = chiave_pubblica(vapid)
    assert len(chiave) == 87
    grezza = base64.urlsafe_b64decode(chiave + "=")
    assert len(grezza) == 65 and grezza[0] == 4
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_push.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.push'`.

- [ ] **Step 3: scrivi il modulo**

`src/rsm/push.py`:

```python
"""Le notifiche Web Push: l'invito, il rinvio, l'esito della validazione.

Due trappole del vero, entrambe in docs/differenze-fra-test-e-realta.md:
- `pywebpush.webpush` scrive dentro `vapid_claims` l'«aud» del primo servizio
  push che incontra: riusare lo stesso dizionario per un'iscrizione di Firefox
  dopo una di Chrome firmerebbe per il destinatario sbagliato (403). Un
  dizionario nuovo a ogni invio.
- il TTL predefinito è 0: un telefono spento perderebbe la notifica. Il TTL lo
  sceglie sempre chi chiama.

Un invio fallito non fa mai fallire l'operazione che l'ha causato: si registra
e si va avanti. Il gruppo Telegram e il polling della pagina restano.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import requests
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid01, b64urlencode
from pywebpush import WebPushException, webpush

from .store import Store

log = logging.getLogger(__name__)

_SCADUTA = (404, 410)


def chiave_pubblica(vapid: Vapid01) -> str:
    """La chiave che la pagina passa a `pushManager.subscribe`."""
    return b64urlencode(
        vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    )


class Notificatore:
    def __init__(
        self,
        store: Store,
        vapid: Vapid01,
        contatto: str,
        invia: Callable[..., Any] = webpush,
    ) -> None:
        self._store = store
        self._vapid = vapid
        self._contatto = contatto
        self._invia = invia

    def a_persona(self, soprannome: str, titolo: str, testo: str, *, ttl: int) -> int:
        """Manda la notifica a tutti i dispositivi iscritti di una persona.

        Restituisce quanti invii il servizio push ha accettato: accettato non
        vuol dire consegnato.
        """
        dati = json.dumps({"titolo": titolo, "testo": testo})
        accettati = 0
        for iscrizione in self._store.iscrizioni_di(soprannome):
            try:
                self._invia(
                    subscription_info={
                        "endpoint": iscrizione.endpoint,
                        "keys": {"p256dh": iscrizione.p256dh, "auth": iscrizione.auth},
                    },
                    data=dati,
                    vapid_private_key=self._vapid,
                    vapid_claims={"sub": self._contatto},
                    ttl=ttl,
                    timeout=10,
                )
            except WebPushException as e:
                stato = getattr(e.response, "status_code", None)
                if stato in _SCADUTA:
                    self._store.togli_iscrizione(iscrizione.endpoint)
                    log.info("iscrizione push di %s scaduta (%s): tolta", soprannome, stato)
                else:
                    log.warning("push a %s rifiutato dal servizio push (%s)", soprannome, stato)
            except (requests.RequestException, OSError) as e:
                log.warning("push a %s non inviato: %s", soprannome, type(e).__name__)
            else:
                accettati += 1
        return accettati
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest tests/test_push.py -q && uv run ruff check src tests`
Expected: tutti PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/push.py tests/test_push.py
git commit -m "Web Push sender: fresh VAPID claims per send, explicit TTL

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: configurazione, finti e pulsanti

Tre pezzi piccoli che il servizio usa tutti: la configurazione dall'ambiente (con la sicura e i motivi), i finti dei sistemi esterni per i test, e la codifica dei pulsanti del messaggio di validazione.

**Files:**
- Create: `src/rsm/config.py`, `src/rsm/pulsanti.py`, `tests/finti.py`
- Test: `tests/test_config.py`, `tests/test_pulsanti.py`

**Interfaces:**
- Consumes: `regole.MOTIVO_MASSIMO`, `regole.soprannome_valido`, `regole.RegolaViolata` (Task 1); `TelegramError`, `Pulsanti` (Task 4).
- Produces (`rsm.config`): `ConfigurazioneErrata(ValueError)`; `@dataclass(frozen=True) Motivo(etichetta: str, testo: str)`; `MOTIVI_PREDEFINITI: tuple[Motivo, ...]`; `@dataclass(frozen=True) Impostazioni(db: Path, cartella_foto: Path, token_bot: str, gruppo_prova: int, gruppo_party: int | None, admin_telegram_id: int, vapid_pem: Path, vapid_contatto: str, rinvio_minuti: int = 10, motivi: tuple[Motivo, ...] = MOTIVI_PREDEFINITI)` con le proprietà `sicura_inserita -> bool` e `gruppo_annuncio -> int`; `da_ambiente(env: Mapping[str, str]) -> Impostazioni`; `percorso_db(env) -> Path`; `url_base(env) -> str`.
- Produces (`rsm.pulsanti`): `DOMANDA_MOTIVO = "Scrivi il motivo per"`; azioni `ACCETTA = "ok"`, `ALTRO = "altro"`, `SENZA_MOTIVO = "no"` (i motivi predefiniti sono `"m0"`, `"m1"`, …); `@dataclass(frozen=True) Tocco(giro_id: int, soprannome: str, versione: int, azione: str)`; `dati_tocco(giro_id, soprannome, versione, azione) -> str`; `leggi_tocco(dati: str) -> Tocco | None`; `tastiera(giro_id, soprannome, versione, motivi) -> Pulsanti`; `motivo_del_pulsante(azione: str, motivi) -> str | None`.
- Produces (`tests.finti`): `TelegramFinto` (attributi `chiamate: list[tuple[str, dict]]`, `guasto: Exception | None`, `aggiornamenti_da_dare: list[dict]`; metodi con le firme di `BotTelegram`; ogni metodo che restituisce un id restituisce 101, 102, …; `di_tipo(nome) -> list[dict]`); `NotificheFinte` (attributo `inviate: list[dict]` con chiavi `soprannome`, `titolo`, `testo`, `ttl`; `a_persona(...) -> 1`); `Orologio(inizio)` (chiamabile; `adesso`; `avanza(**timedelta)`); `impostazioni_di_prova(cartella: Path, **cambi) -> Impostazioni` (gruppo di prova `-100`, admin `123456789`, sicura inserita).

- [ ] **Step 1: scrivi i finti**

`tests/finti.py`:

```python
"""I finti dei sistemi esterni.

Ognuno mette per iscritto una convinzione sul vero: dove quella convinzione
viene messa alla prova lo dice docs/differenze-fra-test-e-realta.md. Prima di
aggiungere un comportamento qui, la domanda è: quale convinzione sto scrivendo,
e dove la verifica il piano reale?
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from rsm.config import Impostazioni
from rsm.telegram import TelegramError


class TelegramFinto:
    """Risponde sempre subito e con successo, finché `guasto` non è impostato."""

    def __init__(self) -> None:
        self.chiamate: list[tuple[str, dict]] = []
        self.guasto: Exception | None = None
        self.aggiornamenti_da_dare: list[dict] = []
        self._ultimo_id = 100

    def _registra(self, nome: str, **argomenti) -> int:
        if self.guasto is not None:
            raise self.guasto
        self.chiamate.append((nome, argomenti))
        self._ultimo_id += 1
        return self._ultimo_id

    def scrivi(self, chat_id, testo):
        return self._registra("scrivi", chat_id=chat_id, testo=testo)

    def manda_foto(self, chat_id, dati, didascalia, pulsanti):
        return self._registra(
            "manda_foto", chat_id=chat_id, dati=dati, didascalia=didascalia, pulsanti=pulsanti
        )

    def modifica_didascalia(self, chat_id, messaggio, testo, pulsanti=None):
        self._registra(
            "modifica_didascalia", chat_id=chat_id, messaggio=messaggio, testo=testo, pulsanti=pulsanti
        )

    def chiedi_risposta(self, chat_id, testo):
        return self._registra("chiedi_risposta", chat_id=chat_id, testo=testo)

    def rispondi_tocco(self, tocco_id, testo):
        self._registra("rispondi_tocco", tocco_id=tocco_id, testo=testo)

    def aggiornamenti(self, offset, attesa):
        self._registra("aggiornamenti", offset=offset, attesa=attesa)
        dati, self.aggiornamenti_da_dare = self.aggiornamenti_da_dare, []
        return dati

    def webhook_attivo(self):
        return False

    def di_tipo(self, nome: str) -> list[dict]:
        return [argomenti for n, argomenti in self.chiamate if n == nome]


def telegram_guasto() -> TelegramError:
    return TelegramError("sendMessage: errore di rete (ConnectError)")


class NotificheFinte:
    """Ogni push è accettato. Nel vero accettato non vuol dire consegnato."""

    def __init__(self) -> None:
        self.inviate: list[dict] = []

    def a_persona(self, soprannome, titolo, testo, *, ttl):
        self.inviate.append({"soprannome": soprannome, "titolo": titolo, "testo": testo, "ttl": ttl})
        return 1


class Orologio:
    def __init__(self, inizio: datetime) -> None:
        self.adesso = inizio

    def __call__(self) -> datetime:
        return self.adesso

    def avanza(self, **quanto) -> None:
        self.adesso += timedelta(**quanto)


def impostazioni_di_prova(cartella: Path, **cambi) -> Impostazioni:
    base = Impostazioni(
        db=cartella / "rsm.sqlite",
        cartella_foto=cartella / "foto",
        token_bot="finto",
        gruppo_prova=-100,
        gruppo_party=None,
        admin_telegram_id=123456789,
        vapid_pem=cartella / "vapid.pem",
        vapid_contatto="mailto:prova@example.org",
    )
    return replace(base, **cambi)
```

- [ ] **Step 2: scrivi i test di configurazione e pulsanti**

`tests/test_config.py`:

```python
import json

import pytest

from rsm import config

AMBIENTE = {
    "RSM_DB": "/data/rsm.sqlite",
    "RSM_FOTO": "/data/foto",
    "RSM_BOT_TOKEN": "123:abc",
    "RSM_GRUPPO_PROVA": "-4000",
    "RSM_GRUPPO": "",
    "RSM_ADMIN_TELEGRAM_ID": "123456789",
    "RSM_VAPID_PEM": "/config/vapid.pem",
    "RSM_VAPID_CONTATTO": "mailto:qualcuno@example.org",
}


def test_ambiente_completo_con_la_sicura_inserita():
    imp = config.da_ambiente(AMBIENTE)
    assert imp.sicura_inserita
    assert imp.gruppo_annuncio == -4000
    assert imp.rinvio_minuti == 10
    assert str(imp.db) == "/data/rsm.sqlite"
    assert imp.admin_telegram_id == 123456789


def test_con_il_party_la_sicura_e_armata():
    imp = config.da_ambiente({**AMBIENTE, "RSM_GRUPPO": "-987654321"})
    assert not imp.sicura_inserita
    assert imp.gruppo_annuncio == -987654321


def test_i_quattro_motivi_predefiniti():
    motivi = config.da_ambiente(AMBIENTE).motivi
    assert [m.etichetta for m in motivi] == ["Sfocata", "Troppo buia", "Viso non inquadrato", "Tagliata"]
    assert motivi[3].testo == "tagliata (controlla che tutta la testa sia ben visibile nella foto)"


def test_motivi_personalizzati():
    grezzi = json.dumps([{"etichetta": "Mossa", "testo": "mossa"}])
    assert config.da_ambiente({**AMBIENTE, "RSM_MOTIVI": grezzi}).motivi == (config.Motivo("Mossa", "mossa"),)


@pytest.mark.parametrize(
    "grezzi",
    ["non json", "[]", json.dumps([{"etichetta": "x"}]), json.dumps([{"etichetta": "", "testo": "x"}])],
)
def test_motivi_malformati(grezzi):
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_MOTIVI"):
        config.da_ambiente({**AMBIENTE, "RSM_MOTIVI": grezzi})


@pytest.mark.parametrize("nome", ["RSM_DB", "RSM_BOT_TOKEN", "RSM_GRUPPO_PROVA", "RSM_ADMIN_TELEGRAM_ID"])
def test_una_variabile_mancante_si_nomina(nome):
    with pytest.raises(config.ConfigurazioneErrata, match=nome):
        config.da_ambiente({**AMBIENTE, nome: ""})


def test_un_gruppo_non_numerico():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_GRUPPO_PROVA"):
        config.da_ambiente({**AMBIENTE, "RSM_GRUPPO_PROVA": "gruppo"})


def test_il_contatto_vapid_deve_essere_mailto_o_https():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_VAPID_CONTATTO"):
        config.da_ambiente({**AMBIENTE, "RSM_VAPID_CONTATTO": "qualcuno@example.org"})


def test_il_rinvio_deve_durare_almeno_un_minuto():
    with pytest.raises(config.ConfigurazioneErrata, match="RSM_RINVIO_MINUTI"):
        config.da_ambiente({**AMBIENTE, "RSM_RINVIO_MINUTI": "0"})


def test_url_base():
    assert config.url_base({"RSM_URL_BASE": "https://selfie.example.org/"}) == "https://selfie.example.org"
    assert config.url_base({"RSM_URL_BASE": "http://127.0.0.1:8000"}) == "http://127.0.0.1:8000"
    with pytest.raises(config.ConfigurazioneErrata, match="https"):
        config.url_base({"RSM_URL_BASE": "http://selfie.example.org"})
```

`tests/test_pulsanti.py`:

```python
import pytest

from rsm import pulsanti
from rsm.config import MOTIVI_PREDEFINITI


def test_andata_e_ritorno():
    dati = pulsanti.dati_tocco(12, "jean-paul", 3, "m1")
    assert pulsanti.leggi_tocco(dati) == pulsanti.Tocco(12, "jean-paul", 3, "m1")


def test_il_caso_peggiore_sta_nei_64_byte_di_telegram():
    assert len(pulsanti.dati_tocco(999999, "x" * 32, 9999, "altro").encode()) <= 64


@pytest.mark.parametrize("dati", ["", "x|1|emi|1|ok", "v|uno|emi|1|ok", "v|1|../x|1|ok", "v|1|emi|1"])
def test_dati_estranei_non_si_leggono(dati):
    assert pulsanti.leggi_tocco(dati) is None


def test_la_tastiera():
    righe = pulsanti.tastiera(1, "emi", 2, MOTIVI_PREDEFINITI)
    testi = [[testo for testo, _ in riga] for riga in righe]
    assert testi == [
        ["✅ Va bene"],
        ["Sfocata", "Troppo buia"],
        ["Viso non inquadrato", "Tagliata"],
        ["✏️ Altro motivo…", "🔄 Un'altra, senza motivo"],
    ]
    assert righe[1][1][1] == "v|1|emi|2|m1"


def test_il_motivo_del_pulsante():
    assert pulsanti.motivo_del_pulsante("m1", MOTIVI_PREDEFINITI) == "troppo buia"
    assert pulsanti.motivo_del_pulsante("m9", MOTIVI_PREDEFINITI) is None
    assert pulsanti.motivo_del_pulsante("ok", MOTIVI_PREDEFINITI) is None
    assert pulsanti.motivo_del_pulsante("mx", MOTIVI_PREDEFINITI) is None
```

- [ ] **Step 3: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_config.py tests/test_pulsanti.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.config'`.

- [ ] **Step 4: scrivi configurazione e pulsanti**

`src/rsm/config.py`:

```python
"""La configurazione del servizio, dall'ambiente.

Sul server la contiene tutta `config/rsm.env` (permessi 600); nel repository
c'è solo `config.esempio/rsm.env`. Un valore mancante o malformato ferma
l'avvio con un messaggio che nomina la variabile: mai un default silenzioso per
un segreto o per un gruppo Telegram.

La sicura: finché `RSM_GRUPPO` è vuoto, l'annuncio va nel gruppo di prova. Si
arma scrivendo l'identificativo del party in quel file, dopo la prova generale:
così resta traccia in un file che si rilegge.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .regole import MOTIVO_MASSIMO


class ConfigurazioneErrata(ValueError):
    """Una variabile d'ambiente manca o non ha la forma attesa."""


@dataclass(frozen=True)
class Motivo:
    etichetta: str  # sul pulsante: corta, o Telegram la taglia sul telefono
    testo: str  # per il giocatore: può essere più lungo


MOTIVI_PREDEFINITI = (
    Motivo("Sfocata", "sfocata"),
    Motivo("Troppo buia", "troppo buia"),
    Motivo("Viso non inquadrato", "viso non inquadrato"),
    Motivo("Tagliata", "tagliata (controlla che tutta la testa sia ben visibile nella foto)"),
)


@dataclass(frozen=True)
class Impostazioni:
    db: Path
    cartella_foto: Path
    token_bot: str
    gruppo_prova: int
    gruppo_party: int | None
    admin_telegram_id: int
    vapid_pem: Path
    vapid_contatto: str
    rinvio_minuti: int = 10
    motivi: tuple[Motivo, ...] = MOTIVI_PREDEFINITI

    @property
    def sicura_inserita(self) -> bool:
        return self.gruppo_party is None

    @property
    def gruppo_annuncio(self) -> int:
        return self.gruppo_prova if self.gruppo_party is None else self.gruppo_party


def _testo(env: Mapping[str, str], nome: str) -> str:
    valore = (env.get(nome) or "").strip()
    if not valore:
        raise ConfigurazioneErrata(f"{nome} manca")
    return valore


def _intero(env: Mapping[str, str], nome: str, predefinito: int | None = None) -> int:
    grezzo = (env.get(nome) or "").strip()
    if not grezzo:
        if predefinito is None:
            raise ConfigurazioneErrata(f"{nome} manca")
        return predefinito
    try:
        return int(grezzo)
    except ValueError:
        raise ConfigurazioneErrata(f"{nome} non è un numero intero: {grezzo!r}") from None


def _motivi(env: Mapping[str, str]) -> tuple[Motivo, ...]:
    grezzo = (env.get("RSM_MOTIVI") or "").strip()
    if not grezzo:
        return MOTIVI_PREDEFINITI
    try:
        lista = json.loads(grezzo)
    except json.JSONDecodeError:
        raise ConfigurazioneErrata("RSM_MOTIVI non è JSON valido") from None
    if not isinstance(lista, list) or not 1 <= len(lista) <= 8:
        raise ConfigurazioneErrata("RSM_MOTIVI deve essere una lista di 1-8 motivi")
    motivi = []
    for voce in lista:
        if not (
            isinstance(voce, dict)
            and isinstance(voce.get("etichetta"), str)
            and isinstance(voce.get("testo"), str)
        ):
            raise ConfigurazioneErrata("RSM_MOTIVI: ogni motivo ha «etichetta» e «testo»")
        etichetta, testo = voce["etichetta"].strip(), voce["testo"].strip()
        if not 0 < len(etichetta) <= 30 or not 0 < len(testo) <= MOTIVO_MASSIMO:
            raise ConfigurazioneErrata(
                f"RSM_MOTIVI: etichetta fino a 30 caratteri, testo fino a {MOTIVO_MASSIMO}"
            )
        motivi.append(Motivo(etichetta, testo))
    return tuple(motivi)


def _contatto(env: Mapping[str, str]) -> str:
    contatto = _testo(env, "RSM_VAPID_CONTATTO")
    if not contatto.startswith(("mailto:", "https://")):
        raise ConfigurazioneErrata("RSM_VAPID_CONTATTO deve iniziare con mailto: o https://")
    return contatto


def da_ambiente(env: Mapping[str, str]) -> Impostazioni:
    rinvio = _intero(env, "RSM_RINVIO_MINUTI", 10)
    if rinvio < 1:
        raise ConfigurazioneErrata("RSM_RINVIO_MINUTI deve essere almeno 1")
    party = (env.get("RSM_GRUPPO") or "").strip()
    return Impostazioni(
        db=Path(_testo(env, "RSM_DB")),
        cartella_foto=Path(_testo(env, "RSM_FOTO")),
        token_bot=_testo(env, "RSM_BOT_TOKEN"),
        gruppo_prova=_intero(env, "RSM_GRUPPO_PROVA"),
        gruppo_party=_intero(env, "RSM_GRUPPO") if party else None,
        admin_telegram_id=_intero(env, "RSM_ADMIN_TELEGRAM_ID"),
        vapid_pem=Path(_testo(env, "RSM_VAPID_PEM")),
        vapid_contatto=_contatto(env),
        rinvio_minuti=rinvio,
        motivi=_motivi(env),
    )


def percorso_db(env: Mapping[str, str]) -> Path:
    return Path(_testo(env, "RSM_DB"))


def url_base(env: Mapping[str, str]) -> str:
    base = _testo(env, "RSM_URL_BASE").rstrip("/")
    locale = base.startswith(("http://127.0.0.1", "http://localhost"))
    if not (base.startswith("https://") or locale):
        raise ConfigurazioneErrata("RSM_URL_BASE deve essere un indirizzo https")
    return base
```

`src/rsm/pulsanti.py`:

```python
"""I pulsanti del messaggio di validazione, e la loro codifica.

Telegram restituisce solo la stringa `callback_data`, al massimo 64 byte: dentro
c'è tutto ciò che serve per decidere senza ambiguità — giro, persona, versione
della foto, azione. La versione rende innocuo un tocco su una foto nel frattempo
sostituita.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from . import regole
from .config import Motivo
from .telegram import Pulsanti

DOMANDA_MOTIVO = "Scrivi il motivo per"
ACCETTA = "ok"
ALTRO = "altro"
SENZA_MOTIVO = "no"
_PREFISSO = "v"


@dataclass(frozen=True)
class Tocco:
    giro_id: int
    soprannome: str
    versione: int
    azione: str


def dati_tocco(giro_id: int, soprannome: str, versione: int, azione: str) -> str:
    dati = f"{_PREFISSO}|{int(giro_id)}|{soprannome}|{int(versione)}|{azione}"
    if len(dati.encode("utf-8")) > 64:
        raise ValueError("callback_data oltre i 64 byte ammessi da Telegram")
    return dati


def leggi_tocco(dati: str) -> Tocco | None:
    parti = dati.split("|")
    if len(parti) != 5 or parti[0] != _PREFISSO:
        return None
    try:
        giro_id, versione = int(parti[1]), int(parti[3])
        soprannome = regole.soprannome_valido(parti[2])
    except (ValueError, regole.RegolaViolata):
        return None
    return Tocco(giro_id, soprannome, versione, parti[4])


def tastiera(giro_id: int, soprannome: str, versione: int, motivi: Sequence[Motivo]) -> Pulsanti:
    def pulsante(testo: str, azione: str) -> tuple[str, str]:
        return (testo, dati_tocco(giro_id, soprannome, versione, azione))

    righe: Pulsanti = [[pulsante("✅ Va bene", ACCETTA)]]
    per_motivo = [pulsante(m.etichetta, f"m{i}") for i, m in enumerate(motivi)]
    righe += [per_motivo[i : i + 2] for i in range(0, len(per_motivo), 2)]
    righe.append(
        [pulsante("✏️ Altro motivo…", ALTRO), pulsante("🔄 Un'altra, senza motivo", SENZA_MOTIVO)]
    )
    return righe


def motivo_del_pulsante(azione: str, motivi: Sequence[Motivo]) -> str | None:
    """Il testo per il giocatore del motivo predefinito scelto, o None."""
    if not azione.startswith("m"):
        return None
    try:
        indice = int(azione[1:])
    except ValueError:
        return None
    if not 0 <= indice < len(motivi):
        return None
    return motivi[indice].testo
```

- [ ] **Step 5: lancia i test e verifica che passino**

Run: `uv run pytest tests/test_config.py tests/test_pulsanti.py -q && uv run ruff check src tests`
Expected: tutti PASS.

- [ ] **Step 6: commit**

```bash
git add src/rsm/config.py src/rsm/pulsanti.py tests/finti.py tests/test_config.py tests/test_pulsanti.py
git commit -m "config from env with the safety catch, fakes, validation buttons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: il servizio — giro, foto, rinvio, stato per la pagina

Il cuore del servizio, prima parte: aprire il giro, ricevere una foto, annunciarla ad Alberto, rimandare l'invito, e dire alla pagina com'è la situazione. Ciò che parla con Telegram o col push e non serve alla risposta (`invita`, `annuncia_foto`) è un metodo a parte, che l'HTTP (Task 12) esegue dopo aver risposto.

**Files:**
- Create: `src/rsm/servizio.py`
- Modify: `tests/conftest.py` (sostituisci il contenuto)
- Test: `tests/test_servizio_giro.py`

**Interfaces:**
- Consumes: tutto `rsm.regole` (Task 1); `rsm.foto`, `rsm.gettoni` (Task 2); `Store`, `Foto`, `Persona` (Task 3); `TelegramError`, `Pulsanti` (Task 4); `Impostazioni` (Task 6); `pulsanti.tastiera` (Task 6).
- Produces (`rsm.servizio`): costanti `TITOLO = "📸 Selfie per la miniatura"`, `TESTO_INVITO_GRUPPO = "📸 È il momento del selfie per la miniatura!"`, `TESTO_INVITO_PUSH = "È il momento del selfie!"`, `TESTO_ACCETTATA = "La tua foto è stata accettata"`, `TESTO_ALTRA_FOTO = "Alberto chiede un'altra foto"`, `TTL_INVITO = 1800`, `TTL_ESITO = 43200`; eccezioni `ErroreServizio` (attributo `codice`), `RichiestaErrata` (400), `NonTrovato` (404), `Conflitto` (409), `GiroChiuso` (410); `@dataclass(frozen=True) Ricevuta(foto: Foto, messaggio_da_ritirare: int | None)`; classe `Servizio(*, store, cartella_foto, telegram, notifiche, impostazioni, chiave_vapid: str, ora=lambda: datetime.now(UTC))` con: `persona(gettone: str) -> Persona | None`; `stato(persona) -> dict`; `apri_giro(persona) -> dict` (`{"giro": {...}, "nuovo": bool, "annuncio": {"esito": "inviato" | "fallito", "gruppo": "prova" | "party"} | None}`); `invita(escluso: str) -> None`; `ricevi_foto(persona, giro_id: int, dati: bytes) -> Ricevuta`; `annuncia_foto(giro_id, soprannome, versione, ritira: int | None) -> None`; `rinvia(persona, giro_id) -> datetime`. Il JSON di un giro è `{"id", "aperto_alle", "scade_alle", "sessione"}` con date ISO. `stato()` restituisce `{"persona", "ruolo", "ora", "vapid", "giro", "foto": {"stato", "sha256", "motivo"} | None, "rinvio_fino_a"}` più `"pannello": [{"soprannome", "stato"}]` per master e admin.
- Produces (`tests/conftest.py`): fixture `store`, `orologio` (parte da `INIZIO = 2026-10-04 19:30 UTC`), `telegram` (`TelegramFinto`), `notifiche` (`NotificheFinte`), `impostazioni` (`impostazioni_di_prova`), `servizio` (con `chiave_vapid="CHIAVE-PUBBLICA"`), `persone` (dizionario soprannome → `(Persona, gettone)` per abe admin, gio master, emi e sem giocatori, ctc).

- [ ] **Step 1: estendi le fixture**

`tests/conftest.py` (contenuto completo):

```python
from datetime import UTC, datetime

import pytest

from rsm import gettoni
from rsm.servizio import Servizio
from rsm.store import Store
from tests.finti import NotificheFinte, Orologio, TelegramFinto, impostazioni_di_prova

INIZIO = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)
TAVOLO = [
    ("abe", "admin"),
    ("gio", "master"),
    ("emi", "giocatore"),
    ("sem", "giocatore"),
    ("ctc", "ctc"),
]


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "rsm.sqlite")
    s.crea_schema()
    return s


@pytest.fixture
def orologio():
    return Orologio(INIZIO)


@pytest.fixture
def telegram():
    return TelegramFinto()


@pytest.fixture
def notifiche():
    return NotificheFinte()


@pytest.fixture
def impostazioni(tmp_path):
    return impostazioni_di_prova(tmp_path)


@pytest.fixture
def servizio(store, telegram, notifiche, impostazioni, orologio):
    return Servizio(
        store=store,
        cartella_foto=impostazioni.cartella_foto,
        telegram=telegram,
        notifiche=notifiche,
        impostazioni=impostazioni,
        chiave_vapid="CHIAVE-PUBBLICA",
        ora=orologio,
    )


@pytest.fixture
def persone(store):
    """Il tavolo di prova: persone["emi"] è la coppia (Persona, gettone)."""
    tavolo = {}
    for soprannome, ruolo in TAVOLO:
        gettone = gettoni.genera()
        store.aggiungi_persona(soprannome, ruolo, gettoni.impronta(gettone))
        tavolo[soprannome] = (store.persona_da_impronta(gettoni.impronta(gettone)), gettone)
    return tavolo
```

- [ ] **Step 2: scrivi i test**

`tests/test_servizio_giro.py`:

```python
from datetime import timedelta

import pytest

from rsm import foto
from rsm.servizio import (
    TESTO_INVITO_GRUPPO,
    TTL_INVITO,
    Conflitto,
    GiroChiuso,
    NonTrovato,
    Servizio,
)
from tests.finti import impostazioni_di_prova, telegram_guasto
from tests.immagini import jpeg, png


def chi(persone, soprannome):
    return persone[soprannome][0]


def apri(servizio, persone):
    return servizio.apri_giro(chi(persone, "gio"))["giro"]["id"]


def test_la_persona_si_riconosce_dal_gettone(servizio, persone):
    persona, gettone = persone["emi"]
    assert servizio.persona(gettone) == persona
    assert servizio.persona("inventato") is None
    assert servizio.persona("") is None


def test_un_giocatore_non_apre_il_giro(servizio, persone):
    with pytest.raises(NonTrovato):
        servizio.apri_giro(chi(persone, "emi"))


def test_il_master_apre_il_giro_e_il_bot_lo_annuncia_nel_gruppo_di_prova(servizio, persone, telegram, orologio):
    risposta = servizio.apri_giro(chi(persone, "gio"))
    assert risposta["nuovo"] is True
    assert risposta["annuncio"] == {"esito": "inviato", "gruppo": "prova"}
    assert risposta["giro"]["aperto_alle"] == orologio.adesso.isoformat()
    assert risposta["giro"]["scade_alle"] == (orologio.adesso + timedelta(hours=48)).isoformat()
    assert telegram.di_tipo("scrivi") == [{"chat_id": -100, "testo": TESTO_INVITO_GRUPPO}]


def test_con_la_sicura_armata_l_annuncio_va_al_party(store, telegram, notifiche, tmp_path, orologio, persone):
    imp = impostazioni_di_prova(tmp_path, gruppo_party=-987654321)
    armato = Servizio(
        store=store, cartella_foto=imp.cartella_foto, telegram=telegram,
        notifiche=notifiche, impostazioni=imp, chiave_vapid="k", ora=orologio,
    )
    assert armato.apri_giro(chi(persone, "abe"))["annuncio"] == {"esito": "inviato", "gruppo": "party"}
    assert telegram.di_tipo("scrivi")[0]["chat_id"] == -987654321


def test_riaprire_entro_12_ore_restituisce_lo_stesso_giro(servizio, persone, telegram, orologio):
    primo = servizio.apri_giro(chi(persone, "gio"))
    orologio.avanza(hours=11, minutes=59)
    secondo = servizio.apri_giro(chi(persone, "abe"))
    assert secondo == {"giro": primo["giro"], "nuovo": False, "annuncio": None}
    assert len(telegram.di_tipo("scrivi")) == 1


def test_dopo_12_ore_il_vecchio_si_chiude_e_se_ne_apre_uno_nuovo(servizio, persone, store, orologio):
    primo = servizio.apri_giro(chi(persone, "gio"))["giro"]
    orologio.avanza(hours=12)
    secondo = servizio.apri_giro(chi(persone, "gio"))["giro"]
    assert secondo["id"] != primo["id"]
    assert store.giro(primo["id"]).chiuso_alle == orologio.adesso


def test_se_telegram_non_risponde_il_giro_si_apre_e_lo_si_dice(servizio, persone, telegram, store):
    telegram.guasto = telegram_guasto()
    risposta = servizio.apri_giro(chi(persone, "gio"))
    assert risposta["nuovo"] is True
    assert risposta["annuncio"] == {"esito": "fallito", "gruppo": "prova"}
    assert store.ultimo_giro() is not None


def test_l_invito_push_va_a_chi_scatta_tranne_chi_ha_aperto(servizio, persone, notifiche):
    servizio.invita("gio")
    assert sorted(n["soprannome"] for n in notifiche.inviate) == ["abe", "emi", "sem"]
    assert all(n["ttl"] == TTL_INVITO for n in notifiche.inviate)


def test_la_foto_di_un_giocatore_arriva_in_attesa(servizio, persone, impostazioni):
    giro_id = apri(servizio, persone)
    dati = jpeg()
    ricevuta = servizio.ricevi_foto(chi(persone, "emi"), giro_id, dati)
    assert (ricevuta.foto.stato, ricevuta.foto.versione) == ("in_attesa", 1)
    assert ricevuta.foto.sha256 == foto.impronta(dati)
    assert ricevuta.messaggio_da_ritirare is None
    assert foto.leggi(impostazioni.cartella_foto, giro_id, "emi", 1) == dati


def test_la_foto_di_alberto_e_accettata_all_arrivo(servizio, persone):
    giro_id = apri(servizio, persone)
    assert servizio.ricevi_foto(chi(persone, "abe"), giro_id, jpeg()).foto.stato == "accettata"


def test_una_foto_nuova_sostituisce_la_vecchia_anche_su_disco(servizio, persone, impostazioni, store):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg(colore=(1, 2, 3)))
    store.imposta_messaggio_bot(giro_id, "emi", 1, 555)
    seconda = servizio.ricevi_foto(emi, giro_id, jpeg(colore=(9, 9, 9)))
    assert seconda.foto.versione == 2
    assert seconda.messaggio_da_ritirare == 555
    assert not foto.percorso(impostazioni.cartella_foto, giro_id, "emi", 1).exists()
    assert foto.percorso(impostazioni.cartella_foto, giro_id, "emi", 2).exists()


def test_una_foto_accettata_non_si_sostituisce_e_non_lascia_file(servizio, persone, impostazioni):
    giro_id = apri(servizio, persone)
    abe = chi(persone, "abe")
    servizio.ricevi_foto(abe, giro_id, jpeg())
    with pytest.raises(Conflitto, match="definitiva"):
        servizio.ricevi_foto(abe, giro_id, jpeg())
    assert sorted(f.name for f in (impostazioni.cartella_foto / str(giro_id)).iterdir()) == ["abe-1.jpg"]


def test_una_foto_non_valida_non_lascia_traccia(servizio, persone, store, impostazioni):
    giro_id = apri(servizio, persone)
    with pytest.raises(foto.FotoNonJpeg):
        servizio.ricevi_foto(chi(persone, "emi"), giro_id, png())
    assert store.foto(giro_id, "emi") is None
    assert not (impostazioni.cartella_foto / str(giro_id)).exists()


def test_giro_inesistente_o_chiuso(servizio, persone, orologio):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    with pytest.raises(NonTrovato):
        servizio.ricevi_foto(emi, 999, jpeg())
    orologio.avanza(hours=48)
    with pytest.raises(GiroChiuso):
        servizio.ricevi_foto(emi, giro_id, jpeg())


def test_ctc_non_scatta(servizio, persone):
    giro_id = apri(servizio, persone)
    with pytest.raises(NonTrovato):
        servizio.ricevi_foto(chi(persone, "ctc"), giro_id, jpeg())


def test_la_foto_da_validare_arriva_ad_alberto_con_i_pulsanti(servizio, persone, telegram, store):
    giro_id = apri(servizio, persone)  # l'annuncio nel gruppo prende l'id 101
    dati = jpeg()
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, dati)
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    [inviata] = telegram.di_tipo("manda_foto")
    assert inviata["chat_id"] == 123456789
    assert inviata["dati"] == dati
    assert inviata["didascalia"] == "Selfie di emi"
    assert inviata["pulsanti"][0] == [("✅ Va bene", f"v|{giro_id}|emi|1|ok")]
    assert store.foto(giro_id, "emi").messaggio_bot == 102


def test_un_annuncio_vecchio_non_parte(servizio, persone, telegram):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    assert telegram.di_tipo("manda_foto") == []


def test_il_messaggio_della_foto_sostituita_si_ritira(servizio, persone, telegram):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 1, None)  # id 102
    seconda = servizio.ricevi_foto(emi, giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 2, seconda.messaggio_da_ritirare)
    [ritiro] = telegram.di_tipo("modifica_didascalia")
    assert ritiro["messaggio"] == 102
    assert ritiro["pulsanti"] is None
    assert ritiro["testo"] == "↩️ Selfie di emi: sostituita da una foto nuova"
    assert len(telegram.di_tipo("manda_foto")) == 2


def test_se_il_bot_non_raggiunge_alberto_la_foto_resta_in_attesa(servizio, persone, telegram, store):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    telegram.guasto = telegram_guasto()
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    foto_emi = store.foto(giro_id, "emi")
    assert (foto_emi.stato, foto_emi.messaggio_bot) == ("in_attesa", None)


def test_salta_rimanda_di_10_minuti(servizio, persone, orologio):
    giro_id = apri(servizio, persone)
    emi = chi(persone, "emi")
    fino_a = servizio.rinvia(emi, giro_id)
    assert fino_a == orologio.adesso + timedelta(minutes=10)
    assert servizio.stato(emi)["rinvio_fino_a"] == fino_a.isoformat()
    orologio.avanza(minutes=10)
    assert servizio.stato(emi)["rinvio_fino_a"] is None


def test_lo_stato_senza_giro(servizio, persone, orologio):
    assert servizio.stato(chi(persone, "emi")) == {
        "persona": "emi",
        "ruolo": "giocatore",
        "ora": orologio.adesso.isoformat(),
        "vapid": "CHIAVE-PUBBLICA",
        "giro": None,
        "foto": None,
        "rinvio_fino_a": None,
    }


def test_lo_stato_con_la_foto(servizio, persone):
    giro_id = apri(servizio, persone)
    dati = jpeg()
    emi = chi(persone, "emi")
    servizio.ricevi_foto(emi, giro_id, dati)
    stato = servizio.stato(emi)
    assert stato["giro"]["id"] == giro_id
    assert stato["foto"] == {"stato": "in_attesa", "sha256": foto.impronta(dati), "motivo": None}
    assert "pannello" not in stato


def test_il_pannello_di_master_e_admin(servizio, persone):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    servizio.ricevi_foto(chi(persone, "abe"), giro_id, jpeg())
    servizio.rinvia(chi(persone, "sem"), giro_id)
    pannello = servizio.stato(chi(persone, "gio"))["pannello"]
    assert pannello == [
        {"soprannome": "abe", "stato": "accettata"},
        {"soprannome": "emi", "stato": "in_attesa"},
        {"soprannome": "gio", "stato": "nessuna"},
        {"soprannome": "sem", "stato": "rinviato"},
    ]
    assert servizio.stato(chi(persone, "abe"))["pannello"] == pannello
```

- [ ] **Step 3: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_servizio_giro.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.servizio'` (anche le altre suite falliscono all'import di `conftest.py`: è atteso fino allo step 5).

- [ ] **Step 4: scrivi il servizio**

`src/rsm/servizio.py`:

```python
"""Il cuore del servizio: le operazioni che la pagina, il bot e `ctc` chiedono.

Qui si incontrano le regole (pure), lo store, le foto su disco, Telegram e il
push. Le rotte HTTP e il bot restano sottili: chiamano questi metodi e ne
traducono le eccezioni. Ciò che parla con un sistema esterno lento e non serve
alla risposta (`invita`, `annuncia_foto`, `dopo_decisione`) sta in un metodo a
parte, che l'HTTP esegue dopo aver risposto.

Un guasto di Telegram o del push non fa mai fallire l'operazione: si registra,
e la risposta dice la verità su cosa è partito e cosa no.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from . import foto, gettoni, pulsanti, regole
from .config import Impostazioni
from .regole import Giro
from .store import Foto, Persona, Store
from .telegram import Pulsanti, TelegramError

log = logging.getLogger(__name__)

TITOLO = "📸 Selfie per la miniatura"
TESTO_INVITO_GRUPPO = "📸 È il momento del selfie per la miniatura!"
TESTO_INVITO_PUSH = "È il momento del selfie!"
TESTO_ACCETTATA = "La tua foto è stata accettata"
TESTO_ALTRA_FOTO = "Alberto chiede un'altra foto"
TTL_INVITO = 30 * 60
TTL_ESITO = 12 * 60 * 60


class ErroreServizio(Exception):
    codice = 400


class RichiestaErrata(ErroreServizio):
    codice = 400


class NonTrovato(ErroreServizio):
    codice = 404


class Conflitto(ErroreServizio):
    codice = 409


class GiroChiuso(ErroreServizio):
    codice = 410


class Telegram(Protocol):
    def scrivi(self, chat_id: int, testo: str) -> int: ...

    def manda_foto(self, chat_id: int, dati: bytes, didascalia: str, pulsanti: Pulsanti) -> int: ...

    def modifica_didascalia(
        self, chat_id: int, messaggio: int, testo: str, pulsanti: Pulsanti | None = None
    ) -> None: ...

    def chiedi_risposta(self, chat_id: int, testo: str) -> int: ...


class Notifiche(Protocol):
    def a_persona(self, soprannome: str, titolo: str, testo: str, *, ttl: int) -> int: ...


@dataclass(frozen=True)
class Ricevuta:
    foto: Foto
    messaggio_da_ritirare: int | None  # il messaggio del bot per la versione sostituita


def _iso(momento: datetime) -> str:
    return momento.astimezone(UTC).isoformat()


class Servizio:
    def __init__(
        self,
        *,
        store: Store,
        cartella_foto: Path,
        telegram: Telegram,
        notifiche: Notifiche,
        impostazioni: Impostazioni,
        chiave_vapid: str,
        ora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._cartella = cartella_foto
        self._telegram = telegram
        self._notifiche = notifiche
        self._imp = impostazioni
        self._chiave_vapid = chiave_vapid
        self._ora = ora

    # --- identità

    def persona(self, gettone: str) -> Persona | None:
        if not gettone:
            return None
        return self._store.persona_da_impronta(gettoni.impronta(gettone))

    def _richiedi(self, persona: Persona, ruoli: frozenset[str]) -> None:
        if persona.ruolo not in ruoli:
            raise NonTrovato("operazione inesistente")

    # --- giro

    def _giro_json(self, giro: Giro) -> dict:
        return {
            "id": giro.id,
            "aperto_alle": _iso(giro.aperto_alle),
            "scade_alle": _iso(regole.fine(giro)),
            "sessione": giro.sessione,
        }

    def _giro_aperto(self) -> Giro | None:
        giro = self._store.ultimo_giro()
        if giro is None or not regole.aperto(giro, self._ora()):
            return None
        return giro

    def _giro_aperto_da_id(self, giro_id: int) -> Giro:
        giro = self._store.giro(giro_id)
        if giro is None:
            raise NonTrovato("giro inesistente")
        if not regole.aperto(giro, self._ora()):
            raise GiroChiuso("il giro è chiuso")
        return giro

    def apri_giro(self, persona: Persona) -> dict:
        self._richiedi(persona, regole.CHI_APRE)
        ora = self._ora()
        decisione = regole.decidi_apertura(self._store.ultimo_giro(), ora)
        if decisione.riusa is not None:
            return {"giro": self._giro_json(decisione.riusa), "nuovo": False, "annuncio": None}
        if decisione.chiudi is not None:
            self._store.chiudi_giro(decisione.chiudi.id, ora)
        giro = self._store.crea_giro(ora, persona.soprannome)
        return {"giro": self._giro_json(giro), "nuovo": True, "annuncio": self._annuncia_nel_gruppo()}

    def _annuncia_nel_gruppo(self) -> dict:
        gruppo = "prova" if self._imp.sicura_inserita else "party"
        try:
            self._telegram.scrivi(self._imp.gruppo_annuncio, TESTO_INVITO_GRUPPO)
        except TelegramError as e:
            log.warning("annuncio nel gruppo non partito: %s", e)
            return {"esito": "fallito", "gruppo": gruppo}
        return {"esito": "inviato", "gruppo": gruppo}

    def invita(self, escluso: str) -> None:
        """Il push dell'invito a chi scatta, tranne chi ha aperto il giro."""
        for persona in self._store.persone():
            if persona.ruolo in regole.CHI_SCATTA and persona.soprannome != escluso:
                self._notifiche.a_persona(
                    persona.soprannome, TITOLO, TESTO_INVITO_PUSH, ttl=TTL_INVITO
                )

    # --- foto

    def ricevi_foto(self, persona: Persona, giro_id: int, dati: bytes) -> Ricevuta:
        self._richiedi(persona, regole.CHI_SCATTA)
        self._giro_aperto_da_id(giro_id)
        attuale = self._store.foto(giro_id, persona.soprannome)
        try:
            stato = regole.stato_dopo_invio(attuale.stato if attuale else None, persona.ruolo)
        except regole.RegolaViolata as e:
            raise Conflitto(str(e)) from e
        foto.valida(dati)
        temporaneo = foto.salva_temporaneo(self._cartella, giro_id, persona.soprannome, dati)
        try:
            nuova = self._store.salva_foto(
                giro_id, persona.soprannome, stato, foto.impronta(dati), len(dati), self._ora()
            )
            if nuova is None:
                raise Conflitto("la foto è già stata accettata: è definitiva")
            foto.promuovi(temporaneo, self._cartella, giro_id, persona.soprannome, nuova.versione)
        finally:
            temporaneo.unlink(missing_ok=True)
        if attuale is not None:
            foto.cancella(self._cartella, giro_id, persona.soprannome, attuale.versione)
        return Ricevuta(nuova, attuale.messaggio_bot if attuale else None)

    def _modifica(self, messaggio: int, testo: str, pulsanti_: Pulsanti | None = None) -> None:
        try:
            self._telegram.modifica_didascalia(
                self._imp.admin_telegram_id, messaggio, testo, pulsanti_
            )
        except TelegramError as e:
            log.warning("messaggio %s del bot non aggiornato: %s", messaggio, e)

    def annuncia_foto(
        self, giro_id: int, soprannome: str, versione: int, ritira: int | None
    ) -> None:
        """Manda ad Alberto la foto da validare, e ritira il messaggio della
        versione sostituita. Se nel frattempo la foto è cambiata o è stata
        decisa, non manda niente: il messaggio sarebbe vecchio."""
        if ritira is not None:
            self._modifica(ritira, f"↩️ Selfie di {soprannome}: sostituita da una foto nuova")
        corrente = self._store.foto(giro_id, soprannome)
        if corrente is None or corrente.versione != versione or corrente.stato != regole.IN_ATTESA:
            return
        dati = foto.leggi(self._cartella, giro_id, soprannome, versione)
        try:
            messaggio = self._telegram.manda_foto(
                self._imp.admin_telegram_id,
                dati,
                f"Selfie di {soprannome}",
                pulsanti.tastiera(giro_id, soprannome, versione, self._imp.motivi),
            )
        except TelegramError as e:
            log.warning("foto di %s non mandata ad Alberto: %s", soprannome, e)
            return
        self._store.imposta_messaggio_bot(giro_id, soprannome, versione, messaggio)

    def rinvia(self, persona: Persona, giro_id: int) -> datetime:
        self._richiedi(persona, regole.CHI_SCATTA)
        self._giro_aperto_da_id(giro_id)
        fino_a = regole.rinvio_fino_a(self._ora(), self._imp.rinvio_minuti)
        self._store.imposta_rinvio(giro_id, persona.soprannome, fino_a)
        return fino_a

    # --- stato per la pagina

    def stato(self, persona: Persona) -> dict:
        ora = self._ora()
        giro = self._giro_aperto()
        risposta: dict = {
            "persona": persona.soprannome,
            "ruolo": persona.ruolo,
            "ora": _iso(ora),
            "vapid": self._chiave_vapid,
            "giro": None,
            "foto": None,
            "rinvio_fino_a": None,
        }
        if giro is not None:
            risposta["giro"] = self._giro_json(giro)
            mia = self._store.foto(giro.id, persona.soprannome)
            if mia is not None:
                risposta["foto"] = {"stato": mia.stato, "sha256": mia.sha256, "motivo": mia.motivo}
            rinvio = self._store.rinvio(giro.id, persona.soprannome)
            if rinvio is not None and rinvio.fino_a > ora:
                risposta["rinvio_fino_a"] = _iso(rinvio.fino_a)
        if persona.ruolo in regole.CHI_APRE:
            risposta["pannello"] = self._pannello(giro, ora)
        return risposta

    def _pannello(self, giro: Giro | None, ora: datetime) -> list[dict]:
        righe = []
        for persona in self._store.persone():
            if persona.ruolo not in regole.CHI_SCATTA:
                continue
            stato_foto, rinvio_attivo = None, False
            if giro is not None:
                sua = self._store.foto(giro.id, persona.soprannome)
                stato_foto = sua.stato if sua else None
                rinvio = self._store.rinvio(giro.id, persona.soprannome)
                rinvio_attivo = rinvio is not None and rinvio.fino_a > ora
            righe.append(
                {
                    "soprannome": persona.soprannome,
                    "stato": regole.stato_pannello(stato_foto, rinvio_attivo),
                }
            )
        return righe
```

- [ ] **Step 5: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 6: commit**

```bash
git add src/rsm/servizio.py tests/conftest.py tests/test_servizio_giro.py
git commit -m "service core: open round, receive photo, announce, snooze, page state

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: il servizio — decisioni e motivi

La validazione: accettare o chiedere un'altra foto, con un motivo facoltativo, e le sue conseguenze (push al giocatore, messaggio del bot aggiornato). Più il percorso di «Altro motivo…»: una domanda in risposta forzata, e il testo che torna. La decisione vale solo sulla versione vista e solo se la foto è ancora in attesa.

**Files:**
- Modify: `src/rsm/servizio.py` (aggiungi quattro metodi in fondo alla classe `Servizio`)
- Test: `tests/test_servizio_decisioni.py`

**Interfaces:**
- Consumes: `Store.decidi`, `Store.imposta_attesa_motivo`, `Store.foto_in_attesa_di_motivo` (Task 3); `regole.verifica_esito`, `regole.motivo_valido` (Task 1); `pulsanti.DOMANDA_MOTIVO`, `pulsanti.tastiera` (Task 6); `Servizio._modifica`, costanti e eccezioni (Task 7).
- Produces (metodi di `Servizio`): `decidi(giro_id, soprannome, versione, esito, motivo) -> Foto` (solleva `NonTrovato`, `Conflitto` per versione sostituita o foto già decisa, `RichiestaErrata` per esito o motivo non validi); `dopo_decisione(decisa: Foto) -> None`; `aspetta_motivo(giro_id, soprannome, versione) -> None` (può lasciar passare `TelegramError` di `chiedi_risposta`); `motivo_scritto(risposta_a: int, testo: str | None) -> Foto | None` (`None` se quella domanda non aspetta più niente; `regole.RegolaViolata` se il testo è vuoto o troppo lungo).

- [ ] **Step 1: scrivi i test**

`tests/test_servizio_decisioni.py`:

```python
import pytest

from rsm import pulsanti, regole
from rsm.config import MOTIVI_PREDEFINITI
from rsm.servizio import TESTO_ACCETTATA, TITOLO, TTL_ESITO, Conflitto, NonTrovato, RichiestaErrata
from tests.finti import telegram_guasto
from tests.immagini import jpeg

TAGLIATA = "tagliata (controlla che tutta la testa sia ben visibile nella foto)"


def chi(persone, soprannome):
    return persone[soprannome][0]


def foto_in_attesa(servizio, persone):
    """Un giro aperto da gio (annuncio: id 101) e la foto di emi annunciata ad Alberto (id 102)."""
    giro_id = servizio.apri_giro(chi(persone, "gio"))["giro"]["id"]
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    servizio.annuncia_foto(giro_id, "emi", 1, None)
    return giro_id


def test_accettare(servizio, persone, store):
    giro_id = foto_in_attesa(servizio, persone)
    decisa = servizio.decidi(giro_id, "emi", 1, "accettata", None)
    assert decisa.stato == "accettata"
    assert store.foto(giro_id, "emi").stato == "accettata"


def test_chiedere_un_altra_foto_con_il_motivo_ripulito(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    decisa = servizio.decidi(giro_id, "emi", 1, "da_rifare", "  troppo buia ")
    assert (decisa.stato, decisa.motivo) == ("da_rifare", "troppo buia")


def test_la_versione_deve_essere_quella_vista(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    with pytest.raises(Conflitto, match="sostituita"):
        servizio.decidi(giro_id, "emi", 1, "accettata", None)


def test_una_foto_gia_decisa_non_si_decide_di_nuovo(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.decidi(giro_id, "emi", 1, "accettata", None)
    with pytest.raises(Conflitto, match="già stata decisa"):
        servizio.decidi(giro_id, "emi", 1, "da_rifare", None)


def test_richieste_sbagliate(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    with pytest.raises(RichiestaErrata):
        servizio.decidi(giro_id, "emi", 1, "accettata", "sfocata")
    with pytest.raises(RichiestaErrata, match="al massimo 200"):
        servizio.decidi(giro_id, "emi", 1, "da_rifare", "x" * 201)
    with pytest.raises(RichiestaErrata, match="sconosciuto"):
        servizio.decidi(giro_id, "emi", 1, "forse", None)
    with pytest.raises(NonTrovato):
        servizio.decidi(giro_id, "sem", 1, "accettata", None)


def test_dopo_l_accettazione_il_push_e_il_messaggio_aggiornato(servizio, persone, notifiche, telegram):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.dopo_decisione(servizio.decidi(giro_id, "emi", 1, "accettata", None))
    assert notifiche.inviate[-1] == {
        "soprannome": "emi", "titolo": TITOLO, "testo": TESTO_ACCETTATA, "ttl": TTL_ESITO,
    }
    [modifica] = telegram.di_tipo("modifica_didascalia")
    assert modifica["messaggio"] == 102
    assert modifica["testo"] == "✅ Selfie di emi: accettata"
    assert modifica["pulsanti"] is None


def test_dopo_la_richiesta_il_push_porta_il_motivo(servizio, persone, notifiche, telegram):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.dopo_decisione(servizio.decidi(giro_id, "emi", 1, "da_rifare", TAGLIATA))
    assert notifiche.inviate[-1]["testo"] == f"Alberto chiede un'altra foto: {TAGLIATA}"
    assert telegram.di_tipo("modifica_didascalia")[-1]["testo"] == (
        f"🔄 Selfie di emi: chiesta un'altra foto — {TAGLIATA}"
    )


def test_dopo_la_richiesta_senza_motivo(servizio, persone, notifiche, telegram):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.dopo_decisione(servizio.decidi(giro_id, "emi", 1, "da_rifare", None))
    assert notifiche.inviate[-1]["testo"] == "Alberto chiede un'altra foto"
    assert telegram.di_tipo("modifica_didascalia")[-1]["testo"] == "🔄 Selfie di emi: chiesta un'altra foto"


def test_la_pagina_vede_il_motivo(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.decidi(giro_id, "emi", 1, "da_rifare", "troppo buia")
    stato = servizio.stato(chi(persone, "emi"))
    assert (stato["foto"]["stato"], stato["foto"]["motivo"]) == ("da_rifare", "troppo buia")


def test_se_telegram_non_risponde_la_decisione_resta(servizio, persone, telegram, store, notifiche):
    giro_id = foto_in_attesa(servizio, persone)
    decisa = servizio.decidi(giro_id, "emi", 1, "accettata", None)
    telegram.guasto = telegram_guasto()
    servizio.dopo_decisione(decisa)
    assert store.foto(giro_id, "emi").stato == "accettata"
    assert notifiche.inviate[-1]["testo"] == TESTO_ACCETTATA


def test_altro_motivo_chiede_il_testo_e_lascia_i_pulsanti(servizio, persone, telegram, store):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    [domanda] = telegram.di_tipo("chiedi_risposta")
    assert domanda["chat_id"] == 123456789
    assert domanda["testo"].startswith(f"{pulsanti.DOMANDA_MOTIVO} emi")
    assert store.foto(giro_id, "emi").attesa_motivo == 103
    [modifica] = telegram.di_tipo("modifica_didascalia")
    assert modifica["testo"] == "✏️ Selfie di emi: aspetto il motivo…"
    assert modifica["pulsanti"] == pulsanti.tastiera(giro_id, "emi", 1, MOTIVI_PREDEFINITI)
    assert store.foto(giro_id, "emi").stato == "in_attesa"


def test_il_motivo_scritto_decide(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    decisa = servizio.motivo_scritto(103, "  hai gli occhi chiusi ")
    assert (decisa.stato, decisa.motivo) == ("da_rifare", "hai gli occhi chiusi")


def test_un_motivo_vuoto_o_troppo_lungo_non_decide(servizio, persone, store):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    with pytest.raises(regole.RegolaViolata, match="al massimo 200"):
        servizio.motivo_scritto(103, "x" * 201)
    with pytest.raises(regole.RegolaViolata, match="vuoto"):
        servizio.motivo_scritto(103, None)
    foto_emi = store.foto(giro_id, "emi")
    assert (foto_emi.stato, foto_emi.attesa_motivo) == ("in_attesa", 103)


def test_una_risposta_a_una_domanda_superata(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.aspetta_motivo(giro_id, "emi", 1)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())  # la foto nuova annulla la domanda
    assert servizio.motivo_scritto(103, "sfocata") is None
    assert servizio.motivo_scritto(999, "sfocata") is None


def test_altro_motivo_su_una_foto_decisa_o_sostituita(servizio, persone):
    giro_id = foto_in_attesa(servizio, persone)
    servizio.decidi(giro_id, "emi", 1, "accettata", None)
    with pytest.raises(Conflitto, match="già stata decisa"):
        servizio.aspetta_motivo(giro_id, "emi", 1)
    sem = chi(persone, "sem")
    servizio.ricevi_foto(sem, giro_id, jpeg())
    servizio.ricevi_foto(sem, giro_id, jpeg())
    with pytest.raises(Conflitto, match="sostituita"):
        servizio.aspetta_motivo(giro_id, "sem", 1)
    with pytest.raises(NonTrovato):
        servizio.aspetta_motivo(giro_id, "nessuno", 1)
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_servizio_decisioni.py -q`
Expected: FAIL, `AttributeError: 'Servizio' object has no attribute 'decidi'`.

- [ ] **Step 3: aggiungi i metodi in fondo alla classe `Servizio`**

In `src/rsm/servizio.py`, dopo `_pannello`:

```python
    # --- decisioni

    def _foto_decidibile(self, giro_id: int, soprannome: str, versione: int) -> Foto:
        corrente = self._store.foto(giro_id, soprannome)
        if corrente is None:
            raise NonTrovato("foto inesistente")
        if corrente.versione != versione:
            raise Conflitto("foto sostituita: nel frattempo ne è arrivata una nuova")
        if corrente.stato != regole.IN_ATTESA:
            raise Conflitto("la foto è già stata decisa")
        return corrente

    def decidi(
        self, giro_id: int, soprannome: str, versione: int, esito: str, motivo: str | None
    ) -> Foto:
        """Accetta la foto o ne chiede un'altra. Vale solo sulla versione vista."""
        self._foto_decidibile(giro_id, soprannome, versione)
        try:
            pulito = regole.verifica_esito(esito, motivo)
        except regole.RegolaViolata as e:
            raise RichiestaErrata(str(e)) from e
        if not self._store.decidi(giro_id, soprannome, versione, esito, pulito):
            raise Conflitto("foto sostituita o già decisa")
        decisa = self._store.foto(giro_id, soprannome)
        assert decisa is not None
        return decisa

    def dopo_decisione(self, decisa: Foto) -> None:
        """Il push al giocatore e il messaggio del bot aggiornato."""
        if decisa.stato == regole.ACCETTATA:
            testo = TESTO_ACCETTATA
            didascalia = f"✅ Selfie di {decisa.soprannome}: accettata"
        else:
            testo = f"{TESTO_ALTRA_FOTO}: {decisa.motivo}" if decisa.motivo else TESTO_ALTRA_FOTO
            didascalia = f"🔄 Selfie di {decisa.soprannome}: chiesta un'altra foto"
            if decisa.motivo:
                didascalia += f" — {decisa.motivo}"
        self._notifiche.a_persona(decisa.soprannome, TITOLO, testo, ttl=TTL_ESITO)
        if decisa.messaggio_bot is not None:
            self._modifica(decisa.messaggio_bot, didascalia)

    def aspetta_motivo(self, giro_id: int, soprannome: str, versione: int) -> None:
        """«Altro motivo…»: chiede il testo ad Alberto. I pulsanti restano, così
        può ancora cambiare idea; una decisione presa li rende innocui."""
        corrente = self._foto_decidibile(giro_id, soprannome, versione)
        domanda = self._telegram.chiedi_risposta(
            self._imp.admin_telegram_id,
            f"{pulsanti.DOMANDA_MOTIVO} {soprannome}, rispondendo a questo messaggio "
            f"(al massimo {regole.MOTIVO_MASSIMO} caratteri).",
        )
        if not self._store.imposta_attesa_motivo(giro_id, soprannome, versione, domanda):
            raise Conflitto("foto sostituita o già decisa")
        if corrente.messaggio_bot is not None:
            self._modifica(
                corrente.messaggio_bot,
                f"✏️ Selfie di {soprannome}: aspetto il motivo…",
                pulsanti.tastiera(giro_id, soprannome, versione, self._imp.motivi),
            )

    def motivo_scritto(self, risposta_a: int, testo: str | None) -> Foto | None:
        """Il testo che Alberto ha scritto in risposta alla domanda `risposta_a`.

        `None` se quella domanda non aspetta più niente (foto sostituita o già
        decisa). `regole.RegolaViolata` se il testo va riscritto: la foto resta
        in attesa dello stesso motivo.
        """
        in_attesa = self._store.foto_in_attesa_di_motivo(risposta_a)
        if in_attesa is None:
            return None
        motivo = regole.motivo_valido(testo or "")
        return self.decidi(
            in_attesa.giro_id, in_attesa.soprannome, in_attesa.versione, regole.DA_RIFARE, motivo
        )
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/servizio.py tests/test_servizio_decisioni.py
git commit -m "service: decisions with optional reason, push and bot follow-up

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: il servizio — il lato di `ctc`, le iscrizioni, i rinvii scaduti, la pulizia

Le operazioni che `ctc` userà (elenco dei giri, legame con la sessione, foto e loro byte, persone per `doctor`), l'iscrizione push della pagina, e i due lavori periodici del pianificatore.

**Files:**
- Modify: `src/rsm/servizio.py` (import e metodi in fondo alla classe)
- Test: `tests/test_servizio_ctc.py`

**Interfaces:**
- Consumes: `Store.giri_dal`, `Store.lega`, `Store.foto_del_giro`, `Store.aggiungi_iscrizione`, `Store.togli_iscrizione`, `Store.rinvii_scaduti`, `Store.segna_rinvio_notificato`, `Store.giri_con_foto`, `Store.cancella_foto_giro`, `Iscrizione` (Task 3); `foto.leggi`, `foto.cancella_giro` (Task 2); `regole.rinvio_da_notificare`, `regole.da_cancellare` (Task 1).
- Produces (metodi di `Servizio`): `giri_dal(dal: datetime) -> list[dict]` (ogni giro con in più `"aperto": bool`); `lega(giro_id, sessione: str) -> dict` (idempotente per la stessa sessione; `Conflitto` se legato a un'altra; `RichiestaErrata` se la sessione non è `AAAA-MM-GG`); `foto_del_giro(giro_id) -> list[dict]` (`{"soprannome", "versione", "stato", "sha256", "motivo"}`); `dati_foto(giro_id, soprannome) -> bytes`; `persone() -> list[dict]` (`{"soprannome", "ruolo"}`, senza `ctc`); `iscrivi(persona, dati: dict) -> None`; `disiscrivi(persona, endpoint: str) -> None`; `notifica_rinvii_scaduti() -> int`; `pulisci() -> int`.

- [ ] **Step 1: scrivi i test**

`tests/test_servizio_ctc.py`:

```python
from datetime import timedelta

import pytest

from rsm import foto
from rsm.servizio import TESTO_INVITO_PUSH, Conflitto, NonTrovato, RichiestaErrata
from tests.immagini import jpeg


def chi(persone, soprannome):
    return persone[soprannome][0]


def apri(servizio, persone):
    return servizio.apri_giro(chi(persone, "gio"))["giro"]["id"]


def test_giri_dal_comprende_il_limite(servizio, persone, orologio):
    primo = apri(servizio, persone)
    orologio.avanza(hours=13)
    secondo = apri(servizio, persone)
    assert [g["id"] for g in servizio.giri_dal(orologio.adesso)] == [secondo]
    elenco = servizio.giri_dal(orologio.adesso - timedelta(hours=13))
    assert [(g["id"], g["aperto"]) for g in elenco] == [(primo, False), (secondo, True)]


def test_legare_e_idempotente_per_la_stessa_sessione(servizio, persone):
    giro_id = apri(servizio, persone)
    assert servizio.lega(giro_id, "2026-10-04")["sessione"] == "2026-10-04"
    assert servizio.lega(giro_id, "2026-10-04")["sessione"] == "2026-10-04"
    with pytest.raises(Conflitto, match="2026-10-04"):
        servizio.lega(giro_id, "2026-10-11")


@pytest.mark.parametrize("sessione", ["4 ottobre", "2026-13-40", ""])
def test_una_sessione_malformata(servizio, persone, sessione):
    giro_id = apri(servizio, persone)
    with pytest.raises(RichiestaErrata):
        servizio.lega(giro_id, sessione)


def test_legare_un_giro_inesistente(servizio):
    with pytest.raises(NonTrovato):
        servizio.lega(999, "2026-10-04")


def test_elenco_e_byte_delle_foto(servizio, persone):
    giro_id = apri(servizio, persone)
    dati_emi = jpeg(colore=(1, 1, 1))
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, dati_emi)
    servizio.ricevi_foto(chi(persone, "abe"), giro_id, jpeg())
    assert servizio.foto_del_giro(giro_id) == [
        {"soprannome": "abe", "versione": 1, "stato": "accettata", "sha256": foto.impronta(jpeg()), "motivo": None},
        {"soprannome": "emi", "versione": 1, "stato": "in_attesa", "sha256": foto.impronta(dati_emi), "motivo": None},
    ]
    assert servizio.dati_foto(giro_id, "emi") == dati_emi
    with pytest.raises(NonTrovato):
        servizio.dati_foto(giro_id, "sem")
    with pytest.raises(NonTrovato):
        servizio.foto_del_giro(999)


def test_se_il_file_e_sparito_lo_si_dice(servizio, persone, impostazioni):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    foto.cancella(impostazioni.cartella_foto, giro_id, "emi", 1)
    with pytest.raises(NonTrovato, match="non c'è più"):
        servizio.dati_foto(giro_id, "emi")


def test_le_persone_per_ctc_doctor(servizio, persone):
    assert servizio.persone() == [
        {"soprannome": "abe", "ruolo": "admin"},
        {"soprannome": "emi", "ruolo": "giocatore"},
        {"soprannome": "gio", "ruolo": "master"},
        {"soprannome": "sem", "ruolo": "giocatore"},
    ]


def test_iscrizione_e_disiscrizione_push(servizio, persone, store):
    emi, sem = chi(persone, "emi"), chi(persone, "sem")
    servizio.iscrivi(emi, {"endpoint": "https://push.example/1", "keys": {"p256dh": "p", "auth": "a"}})
    assert len(store.iscrizioni_di("emi")) == 1
    servizio.disiscrivi(sem, "https://push.example/1")  # non è sua
    assert len(store.iscrizioni_di("emi")) == 1
    servizio.disiscrivi(emi, "https://push.example/1")
    assert store.iscrizioni_di("emi") == []


@pytest.mark.parametrize(
    "dati",
    [
        {"endpoint": "http://push.example/1", "keys": {"p256dh": "p", "auth": "a"}},
        {"endpoint": "https://push.example/1", "keys": {"p256dh": "p"}},
        {"endpoint": "https://push.example/1"},
        {},
    ],
)
def test_iscrizioni_non_valide(servizio, persone, dati):
    with pytest.raises(RichiestaErrata):
        servizio.iscrivi(chi(persone, "emi"), dati)


def test_ctc_non_si_iscrive(servizio, persone):
    with pytest.raises(NonTrovato):
        servizio.iscrivi(chi(persone, "ctc"), {"endpoint": "https://x", "keys": {"p256dh": "p", "auth": "a"}})


def test_il_rinvio_scaduto_si_notifica_una_volta_e_solo_a_chi_non_ha_scattato(servizio, persone, orologio, notifiche):
    giro_id = apri(servizio, persone)
    servizio.rinvia(chi(persone, "emi"), giro_id)
    servizio.rinvia(chi(persone, "sem"), giro_id)
    servizio.ricevi_foto(chi(persone, "sem"), giro_id, jpeg())
    orologio.avanza(minutes=9)
    assert servizio.notifica_rinvii_scaduti() == 0
    orologio.avanza(minutes=1)
    assert servizio.notifica_rinvii_scaduti() == 1
    assert [(n["soprannome"], n["testo"]) for n in notifiche.inviate] == [("emi", TESTO_INVITO_PUSH)]
    assert servizio.notifica_rinvii_scaduti() == 0


def test_nessun_rinvio_notificato_a_giro_chiuso(servizio, persone, orologio, store, notifiche):
    giro_id = apri(servizio, persone)
    servizio.rinvia(chi(persone, "emi"), giro_id)
    orologio.avanza(hours=49)
    assert servizio.notifica_rinvii_scaduti() == 0
    assert notifiche.inviate == []
    assert store.rinvio(giro_id, "emi").notificato is True


def test_la_pulizia_trenta_giorni_dopo_la_fine_del_giro(servizio, persone, orologio, store, impostazioni):
    giro_id = apri(servizio, persone)
    servizio.ricevi_foto(chi(persone, "emi"), giro_id, jpeg())
    orologio.avanza(hours=48, days=30, seconds=-1)
    assert servizio.pulisci() == 0
    orologio.avanza(seconds=1)
    assert servizio.pulisci() == 1
    assert store.foto_del_giro(giro_id) == []
    assert not (impostazioni.cartella_foto / str(giro_id)).exists()
    assert store.giro(giro_id) is not None
    assert servizio.pulisci() == 0
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_servizio_ctc.py -q`
Expected: FAIL, `AttributeError: 'Servizio' object has no attribute 'giri_dal'`.

- [ ] **Step 3: aggiungi import e metodi**

In cima a `src/rsm/servizio.py`, gli import diventano:

```python
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from . import foto, gettoni, pulsanti, regole
from .config import Impostazioni
from .regole import Giro
from .store import Foto, Iscrizione, Persona, Store
from .telegram import Pulsanti, TelegramError
```

Subito dopo la funzione `_iso`, aggiungi:

```python
_SESSIONE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sessione_valida(sessione: str) -> str:
    if not _SESSIONE.fullmatch(sessione or ""):
        raise RichiestaErrata(f"sessione non valida: {sessione!r}")
    try:
        date.fromisoformat(sessione)
    except ValueError:
        raise RichiestaErrata(f"sessione non valida: {sessione!r}") from None
    return sessione
```

In fondo alla classe `Servizio`, dopo `motivo_scritto`:

```python
    # --- il lato di ctc

    def giri_dal(self, dal: datetime) -> list[dict]:
        ora = self._ora()
        return [
            {**self._giro_json(giro), "aperto": regole.aperto(giro, ora)}
            for giro in self._store.giri_dal(dal)
        ]

    def lega(self, giro_id: int, sessione: str) -> dict:
        sessione = _sessione_valida(sessione)
        giro = self._store.giro(giro_id)
        if giro is None:
            raise NonTrovato("giro inesistente")
        if giro.sessione is None:
            self._store.lega(giro_id, sessione)
            giro = self._store.giro(giro_id)
            assert giro is not None
        if giro.sessione != sessione:
            raise Conflitto(f"il giro è già legato alla sessione {giro.sessione}")
        return self._giro_json(giro)

    def foto_del_giro(self, giro_id: int) -> list[dict]:
        if self._store.giro(giro_id) is None:
            raise NonTrovato("giro inesistente")
        return [
            {
                "soprannome": f.soprannome,
                "versione": f.versione,
                "stato": f.stato,
                "sha256": f.sha256,
                "motivo": f.motivo,
            }
            for f in self._store.foto_del_giro(giro_id)
        ]

    def dati_foto(self, giro_id: int, soprannome: str) -> bytes:
        corrente = self._store.foto(giro_id, soprannome)
        if corrente is None:
            raise NonTrovato("foto inesistente")
        try:
            return foto.leggi(self._cartella, giro_id, soprannome, corrente.versione)
        except FileNotFoundError:
            raise NonTrovato("il file della foto non c'è più") from None

    def persone(self) -> list[dict]:
        return [
            {"soprannome": p.soprannome, "ruolo": p.ruolo}
            for p in self._store.persone()
            if p.ruolo != regole.CTC
        ]

    # --- iscrizioni push

    def iscrivi(self, persona: Persona, dati: dict) -> None:
        self._richiedi(persona, regole.CHI_SCATTA)
        endpoint = dati.get("endpoint")
        chiavi = dati.get("keys") if isinstance(dati.get("keys"), dict) else {}
        p256dh, auth = chiavi.get("p256dh"), chiavi.get("auth")
        if not (
            isinstance(endpoint, str) and endpoint.startswith("https://") and len(endpoint) <= 2048
        ):
            raise RichiestaErrata("iscrizione push non valida: endpoint")
        if not all(isinstance(v, str) and 0 < len(v) <= 256 for v in (p256dh, auth)):
            raise RichiestaErrata("iscrizione push non valida: chiavi")
        self._store.aggiungi_iscrizione(Iscrizione(endpoint, persona.soprannome, p256dh, auth))

    def disiscrivi(self, persona: Persona, endpoint: str) -> None:
        self._store.togli_iscrizione(endpoint, soprannome=persona.soprannome)

    # --- lavori periodici

    def notifica_rinvii_scaduti(self) -> int:
        ora = self._ora()
        inviati = 0
        for rinvio in self._store.rinvii_scaduti(ora):
            giro = self._store.giro(rinvio.giro_id)
            sua = self._store.foto(rinvio.giro_id, rinvio.soprannome)
            if (
                giro is not None
                and regole.aperto(giro, ora)
                and regole.rinvio_da_notificare(
                    rinvio.fino_a, rinvio.notificato, sua.stato if sua else None, ora
                )
            ):
                self._notifiche.a_persona(
                    rinvio.soprannome, TITOLO, TESTO_INVITO_PUSH, ttl=TTL_INVITO
                )
                inviati += 1
            self._store.segna_rinvio_notificato(rinvio.giro_id, rinvio.soprannome)
        return inviati

    def pulisci(self) -> int:
        ora = self._ora()
        puliti = 0
        for giro in self._store.giri_con_foto():
            if regole.da_cancellare(giro, ora):
                foto.cancella_giro(self._cartella, giro.id)
                self._store.cancella_foto_giro(giro.id)
                puliti += 1
        return puliti
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/servizio.py tests/test_servizio_ctc.py
git commit -m "service: ctc side, push subscriptions, expired snoozes, retention

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 10: la validazione dal bot

La politica del bot: cosa fare di un tocco su un pulsante e di un messaggio di Alberto. Solo Alberto decide; un pulsante vecchio risponde con il motivo per cui non vale più; un motivo troppo lungo si fa riscrivere, senza decidere niente.

**Files:**
- Create: `src/rsm/validazione.py`
- Test: `tests/test_validazione.py`

**Interfaces:**
- Consumes: `Servizio.decidi`, `Servizio.dopo_decisione`, `Servizio.aspetta_motivo`, `Servizio.motivo_scritto`, `ErroreServizio`, `RichiestaErrata` (Task 7-8); `pulsanti.leggi_tocco`, `pulsanti.motivo_del_pulsante`, `pulsanti.ACCETTA`, `pulsanti.ALTRO`, `pulsanti.SENZA_MOTIVO`, `pulsanti.DOMANDA_MOTIVO`, `Motivo` (Task 6); `TelegramError` (Task 4).
- Produces (`rsm.validazione`): classe `Validatore(servizio, telegram, admin_telegram_id: int, motivi: Sequence[Motivo])` con `gestisci(aggiornamento: dict) -> None`, dove `aggiornamento` è un elemento di `getUpdates` (`{"update_id", "callback_query": {...}}` o `{"update_id", "message": {...}}`).

- [ ] **Step 1: scrivi i test**

`tests/test_validazione.py`:

```python
import pytest

from rsm import pulsanti
from rsm.validazione import Validatore
from tests.finti import telegram_guasto
from tests.immagini import jpeg

ALBERTO = 123456789


@pytest.fixture
def validatore(servizio, telegram, impostazioni):
    return Validatore(servizio, telegram, impostazioni.admin_telegram_id, impostazioni.motivi)


@pytest.fixture
def giro_id(servizio, persone):
    """La foto di emi in attesa, annunciata ad Alberto (messaggio 102)."""
    giro = servizio.apri_giro(persone["gio"][0])["giro"]["id"]
    servizio.ricevi_foto(persone["emi"][0], giro, jpeg())
    servizio.annuncia_foto(giro, "emi", 1, None)
    return giro


def tocco(dati, da=ALBERTO):
    return {"update_id": 1, "callback_query": {"id": "t1", "from": {"id": da}, "data": dati}}


def risposta(testo, domanda, da=ALBERTO):
    return {
        "update_id": 2,
        "message": {
            "message_id": 900,
            "from": {"id": da},
            "text": testo,
            "reply_to_message": {"message_id": domanda["id"], "text": domanda["testo"]},
        },
    }


def ultima_domanda(telegram):
    return {"id": 103, "testo": telegram.di_tipo("chiedi_risposta")[-1]["testo"]}


def test_va_bene_accetta_e_avvisa(validatore, giro_id, store, telegram, notifiche):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA)))
    assert store.foto(giro_id, "emi").stato == "accettata"
    assert telegram.di_tipo("rispondi_tocco")[-1] == {"tocco_id": "t1", "testo": "Accettata"}
    assert notifiche.inviate[-1]["testo"] == "La tua foto è stata accettata"


def test_un_motivo_pronto_chiede_un_altra_foto_con_il_suo_testo(validatore, giro_id, store, notifiche):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, "m3")))
    foto_emi = store.foto(giro_id, "emi")
    assert foto_emi.stato == "da_rifare"
    assert foto_emi.motivo == "tagliata (controlla che tutta la testa sia ben visibile nella foto)"
    assert notifiche.inviate[-1]["testo"] == (
        "Alberto chiede un'altra foto: tagliata (controlla che tutta la testa sia ben visibile nella foto)"
    )


def test_un_altra_senza_motivo(validatore, giro_id, store, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.SENZA_MOTIVO)))
    assert (store.foto(giro_id, "emi").stato, store.foto(giro_id, "emi").motivo) == ("da_rifare", None)
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Chiesta un'altra foto"


def test_solo_alberto_decide(validatore, giro_id, store, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA), da=12345))
    assert store.foto(giro_id, "emi").stato == "in_attesa"
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Solo Alberto può decidere"


@pytest.mark.parametrize("dati", ["spazzatura", "v|1|emi|1|m9", "v|1|emi|1|boh"])
def test_pulsanti_sconosciuti(validatore, giro_id, store, telegram, dati):
    validatore.gestisci(tocco(dati.replace("v|1|", f"v|{giro_id}|")))
    assert store.foto(giro_id, "emi").stato == "in_attesa"
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Pulsante sconosciuto"


def test_un_tocco_su_una_foto_sostituita(validatore, servizio, persone, giro_id, store, telegram):
    servizio.ricevi_foto(persone["emi"][0], giro_id, jpeg())
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA)))
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"].startswith("foto sostituita")
    assert store.foto(giro_id, "emi").stato == "in_attesa"


def test_altro_motivo_poi_il_testo(validatore, giro_id, store, telegram, notifiche):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    assert telegram.di_tipo("rispondi_tocco")[-1]["testo"] == "Scrivi il motivo rispondendo alla domanda"
    validatore.gestisci(risposta("hai gli occhi chiusi", ultima_domanda(telegram)))
    foto_emi = store.foto(giro_id, "emi")
    assert (foto_emi.stato, foto_emi.motivo) == ("da_rifare", "hai gli occhi chiusi")
    assert notifiche.inviate[-1]["testo"] == "Alberto chiede un'altra foto: hai gli occhi chiusi"


def test_un_motivo_troppo_lungo_si_riscrive(validatore, giro_id, store, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    domanda = ultima_domanda(telegram)
    validatore.gestisci(risposta("x" * 201, domanda))
    assert store.foto(giro_id, "emi").stato == "in_attesa"
    avviso = telegram.di_tipo("scrivi")[-1]
    assert avviso["chat_id"] == ALBERTO
    assert "al massimo 200" in avviso["testo"] and "Riscrivilo" in avviso["testo"]
    validatore.gestisci(risposta("mossa", domanda))
    assert store.foto(giro_id, "emi").motivo == "mossa"


def test_una_risposta_a_una_domanda_superata(validatore, giro_id, telegram):
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    domanda = ultima_domanda(telegram)
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ACCETTA)))
    validatore.gestisci(risposta("sfocata", domanda))
    assert telegram.di_tipo("scrivi")[-1]["testo"] == (
        "Nel frattempo quella foto è stata sostituita o già decisa: il motivo non serve più."
    )


def test_i_messaggi_che_non_rispondono_alla_domanda_si_ignorano(validatore, giro_id, telegram):
    prima = len(telegram.chiamate)
    validatore.gestisci({"update_id": 3, "message": {"message_id": 1, "from": {"id": ALBERTO}, "text": "ciao"}})
    validatore.gestisci(risposta("x", {"id": 102, "testo": "Selfie di emi"}))
    validatore.gestisci(risposta("x", {"id": 103, "testo": "Scrivi il motivo per emi"}, da=12345))
    assert len(telegram.chiamate) == prima


def test_se_telegram_non_risponde_alla_richiesta_del_motivo(validatore, giro_id, telegram, store):
    telegram.guasto = telegram_guasto()
    validatore.gestisci(tocco(pulsanti.dati_tocco(giro_id, "emi", 1, pulsanti.ALTRO)))
    assert store.foto(giro_id, "emi").attesa_motivo is None
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_validazione.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.validazione'`.

- [ ] **Step 3: scrivi il validatore**

`src/rsm/validazione.py`:

```python
"""La politica del bot: cosa fare di un tocco su un pulsante e di un messaggio.

Solo Alberto decide. Ogni tocco riceve una risposta (Telegram altrimenti lascia
il pulsante in attesa), e la risposta dice la verità: «Accettata» solo se la
decisione è stata registrata, altrimenti il motivo per cui non lo è.

Un motivo scritto è una risposta alla domanda del bot: si riconosce dal testo
della domanda a cui risponde, così un messaggio qualsiasi di Alberto al bot non
viene preso per un motivo.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from . import pulsanti, regole
from .config import Motivo
from .servizio import ErroreServizio, RichiestaErrata, Servizio
from .telegram import TelegramError

log = logging.getLogger(__name__)


class Validatore:
    def __init__(
        self, servizio: Servizio, telegram, admin_telegram_id: int, motivi: Sequence[Motivo]
    ) -> None:
        self._servizio = servizio
        self._telegram = telegram
        self._admin = admin_telegram_id
        self._motivi = motivi

    def gestisci(self, aggiornamento: dict) -> None:
        if "callback_query" in aggiornamento:
            self._tocco(aggiornamento["callback_query"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])

    def _rispondi(self, tocco_id: str, testo: str) -> None:
        try:
            self._telegram.rispondi_tocco(tocco_id, testo)
        except TelegramError as e:
            log.warning("risposta al tocco non partita: %s", e)

    def _esito(self, azione: str) -> tuple[str, str | None]:
        if azione == pulsanti.ACCETTA:
            return regole.ACCETTATA, None
        if azione == pulsanti.SENZA_MOTIVO:
            return regole.DA_RIFARE, None
        motivo = pulsanti.motivo_del_pulsante(azione, self._motivi)
        if motivo is None:
            raise RichiestaErrata("Pulsante sconosciuto")
        return regole.DA_RIFARE, motivo

    def _tocco(self, dati: dict) -> None:
        tocco_id = dati.get("id", "")
        if dati.get("from", {}).get("id") != self._admin:
            self._rispondi(tocco_id, "Solo Alberto può decidere")
            return
        tocco = pulsanti.leggi_tocco(dati.get("data") or "")
        if tocco is None:
            self._rispondi(tocco_id, "Pulsante sconosciuto")
            return
        if tocco.azione == pulsanti.ALTRO:
            try:
                self._servizio.aspetta_motivo(tocco.giro_id, tocco.soprannome, tocco.versione)
            except ErroreServizio as e:
                self._rispondi(tocco_id, str(e))
            except TelegramError as e:
                log.warning("domanda del motivo non partita: %s", e)
                self._rispondi(tocco_id, "Telegram non ha risposto: riprova")
            else:
                self._rispondi(tocco_id, "Scrivi il motivo rispondendo alla domanda")
            return
        try:
            esito, motivo = self._esito(tocco.azione)
            decisa = self._servizio.decidi(
                tocco.giro_id, tocco.soprannome, tocco.versione, esito, motivo
            )
        except ErroreServizio as e:
            self._rispondi(tocco_id, str(e))
            return
        self._rispondi(tocco_id, "Accettata" if esito == regole.ACCETTATA else "Chiesta un'altra foto")
        self._servizio.dopo_decisione(decisa)

    def _messaggio(self, messaggio: dict) -> None:
        if messaggio.get("from", {}).get("id") != self._admin:
            return
        domanda = messaggio.get("reply_to_message") or {}
        if not (domanda.get("text") or "").startswith(pulsanti.DOMANDA_MOTIVO):
            return
        try:
            decisa = self._servizio.motivo_scritto(domanda["message_id"], messaggio.get("text"))
        except regole.RegolaViolata as e:
            self._scrivi_ad_alberto(f"Non va: {e}. Riscrivilo rispondendo alla stessa domanda.")
            return
        except ErroreServizio as e:
            self._scrivi_ad_alberto(str(e))
            return
        if decisa is None:
            self._scrivi_ad_alberto(
                "Nel frattempo quella foto è stata sostituita o già decisa: il motivo non serve più."
            )
            return
        self._servizio.dopo_decisione(decisa)

    def _scrivi_ad_alberto(self, testo: str) -> None:
        try:
            self._telegram.scrivi(self._admin, testo)
        except TelegramError as e:
            log.warning("messaggio ad Alberto non partito: %s", e)
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/validazione.py tests/test_validazione.py
git commit -m "bot policy: only Alberto decides, reasons by button or reply

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: i cicli di fondo

Due fili nel processo del servizio: uno legge il bot (long polling, 25 secondi) e passa ogni aggiornamento al validatore; l'altro, ogni 30 secondi, manda i rinvii scaduti e fa pulizia. Un aggiornamento che esplode non ferma il ciclo; l'offset si salva dopo averlo gestito, così un riavvio riprende dal punto giusto.

**Files:**
- Create: `src/rsm/cicli.py`
- Test: `tests/test_cicli.py`

**Interfaces:**
- Consumes: `TelegramError` (Task 4); `Store.leggi_valore`, `Store.scrivi_valore` (Task 3); `Validatore.gestisci` (Task 10); `Servizio.notifica_rinvii_scaduti`, `Servizio.pulisci` (Task 9).
- Produces (`rsm.cicli`): `CHIAVE_OFFSET = "offset_bot"`; `ciclo_bot(telegram, validatore, store, fermo: threading.Event, *, attesa: int = 25, pausa_errore: float = 5.0) -> None`; `ciclo_pianificatore(servizio, fermo: threading.Event, *, intervallo: float = 30.0) -> None`; `passo(servizio) -> None`.

- [ ] **Step 1: scrivi i test**

`tests/test_cicli.py`:

```python
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
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_cicli.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.cicli'`.

- [ ] **Step 3: scrivi i cicli**

`src/rsm/cicli.py`:

```python
"""I due cicli di fondo del servizio, ciascuno nel suo filo.

`ciclo_bot` legge il bot in long polling e passa ogni aggiornamento al
validatore. L'offset si salva dopo aver gestito l'aggiornamento: dopo un
riavvio si riparte da lì, e un aggiornamento gestito due volte è innocuo (la
seconda decisione trova la foto già decisa e lo dice).

`ciclo_pianificatore` manda i rinvii scaduti e fa pulizia, ogni 30 secondi.

Nessuno dei due si ferma per un errore: lo registra e continua. Si fermano
solo quando `fermo` è impostato, alla chiusura del servizio.
"""

from __future__ import annotations

import logging
import threading

from .telegram import TelegramError

log = logging.getLogger(__name__)

CHIAVE_OFFSET = "offset_bot"


def ciclo_bot(
    telegram,
    validatore,
    store,
    fermo: threading.Event,
    *,
    attesa: int = 25,
    pausa_errore: float = 5.0,
) -> None:
    salvato = store.leggi_valore(CHIAVE_OFFSET)
    offset = int(salvato) if salvato else None
    while not fermo.is_set():
        try:
            aggiornamenti = telegram.aggiornamenti(offset, attesa)
        except TelegramError as e:
            log.warning("lettura del bot non riuscita: %s", e)
            fermo.wait(pausa_errore)
            continue
        for aggiornamento in aggiornamenti:
            try:
                validatore.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            offset = int(aggiornamento["update_id"]) + 1
            store.scrivi_valore(CHIAVE_OFFSET, str(offset))


def passo(servizio) -> None:
    try:
        inviati = servizio.notifica_rinvii_scaduti()
        if inviati:
            log.info("rinvii notificati: %s", inviati)
    except Exception:
        log.exception("rinvii scaduti non gestiti")
    try:
        puliti = servizio.pulisci()
        if puliti:
            log.info("giri ripuliti delle foto: %s", puliti)
    except Exception:
        log.exception("pulizia non riuscita")


def ciclo_pianificatore(servizio, fermo: threading.Event, *, intervallo: float = 30.0) -> None:
    while not fermo.wait(intervallo):
        passo(servizio)
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/cicli.py tests/test_cicli.py
git commit -m "background loops: bot long polling and scheduler

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: le rotte HTTP e il punto d'ingresso

Le rotte, sottili: autenticano, chiamano il servizio, traducono le eccezioni in codici HTTP, e affidano ai `BackgroundTasks` ciò che non serve alla risposta. Il punto d'ingresso costruisce il servizio vero dall'ambiente, alza il livello del logger `httpx` e avvia i due cicli.

**Files:**
- Create: `src/rsm/app.py`, `src/rsm/principale.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `Servizio` e le sue eccezioni (Task 7-9); `foto.MASSIMO`, `foto.FotoRifiutata`, `foto.FotoTroppoGrande` (Task 2); `regole` (ruoli, `IN_ATTESA`) (Task 1); `Persona` (Task 3); `config.da_ambiente` (Task 6); `BotTelegram` (Task 4); `Notificatore`, `chiave_pubblica` (Task 5); `Validatore` (Task 10); `cicli` (Task 11).
- Produces (`rsm.app`): `CSP` (stringa della Content-Security-Policy); `crea_app(servizio, *, cartella_web: Path, lifespan=None) -> FastAPI`. `cartella_web` contiene `index.html`, `sw.js` e la cartella `static/` (la pagina vera arriva nel Task 15; qui i test usano una cartella finta).
- Produces (`rsm.principale`): `costruisci(env: Mapping[str, str] | None = None, *, avvia_cicli: bool = True) -> FastAPI`, usata da `uvicorn --factory rsm.principale:costruisci`.
- Rotte: `GET /salute`; `GET /p/{gettone}` (308 verso `/p/{gettone}/`); `GET /p/{gettone}/`; `GET /p/{gettone}/manifest.webmanifest`; `GET /p/{gettone}/sw.js`; `GET /api/stato`; `POST /api/giro`; `PUT /api/giro/{giro_id}/foto`; `POST /api/giro/{giro_id}/rinvio`; `POST /api/push`; `DELETE /api/push`; per il ruolo `ctc`: `GET /api/giri?dal=…`, `POST /api/giro/{giro_id}/lega`, `GET /api/giro/{giro_id}/foto`, `GET /api/giro/{giro_id}/foto/{soprannome}`, `POST /api/giro/{giro_id}/foto/{soprannome}/esito`, `GET /api/persone`.

- [ ] **Step 1: scrivi i test**

`tests/test_app.py`:

```python
import logging

import pytest
from fastapi.testclient import TestClient
from py_vapid import Vapid

from rsm import foto
from rsm.app import CSP, crea_app
from rsm.principale import costruisci
from tests.immagini import jpeg, png


@pytest.fixture
def cartella_web(tmp_path):
    web = tmp_path / "web"
    (web / "static").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>pagina</title>")
    (web / "sw.js").write_text("// service worker")
    (web / "static" / "stati.js").write_text("export {};")
    return web


@pytest.fixture
def client(servizio, cartella_web):
    return TestClient(crea_app(servizio, cartella_web=cartella_web))


def con(persone, soprannome):
    return {"Authorization": f"Bearer {persone[soprannome][1]}"}


def apri(client, persone):
    return client.post("/api/giro", headers=con(persone, "gio")).json()["giro"]["id"]


def test_salute(client):
    assert client.get("/salute").json() == {"ok": True}


def test_senza_gettone_o_con_uno_sbagliato_404(client):
    assert client.get("/api/stato").status_code == 404
    assert client.get("/api/stato", headers={"Authorization": "Bearer inventato"}).status_code == 404
    assert client.get("/api/stato", headers={"Authorization": "Basic x"}).status_code == 404


def test_lo_stato(client, persone):
    risposta = client.get("/api/stato", headers=con(persone, "emi"))
    assert risposta.status_code == 200
    assert risposta.json()["persona"] == "emi"


def test_la_pagina_personale(client, persone):
    gettone = persone["emi"][1]
    senza_barra = client.get(f"/p/{gettone}", follow_redirects=False)
    assert senza_barra.status_code == 308
    assert senza_barra.headers["location"] == f"/p/{gettone}/"
    pagina = client.get(f"/p/{gettone}/")
    assert pagina.status_code == 200
    assert "pagina" in pagina.text
    assert pagina.headers["content-security-policy"] == CSP
    assert pagina.headers["cache-control"] == "no-store"
    assert pagina.headers["referrer-policy"] == "no-referrer"
    assert client.get("/p/inventato/").status_code == 404
    assert client.get("/p/inventato", follow_redirects=False).status_code == 404
    assert client.get(f"/p/{persone['ctc'][1]}/").status_code == 404


def test_manifest_e_service_worker_della_persona(client, persone):
    gettone = persone["emi"][1]
    manifest = client.get(f"/p/{gettone}/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.json()["start_url"] == f"/p/{gettone}/"
    assert manifest.json()["scope"] == f"/p/{gettone}/"
    sw = client.get(f"/p/{gettone}/sw.js")
    assert sw.headers["content-type"].startswith("text/javascript")
    assert client.get("/p/inventato/sw.js").status_code == 404


def test_i_file_statici(client):
    assert client.get("/static/stati.js").status_code == 200


def test_aprire_il_giro(client, persone, notifiche, telegram):
    assert client.post("/api/giro", headers=con(persone, "emi")).status_code == 404
    risposta = client.post("/api/giro", headers=con(persone, "gio")).json()
    assert risposta["nuovo"] is True
    assert risposta["annuncio"] == {"esito": "inviato", "gruppo": "prova"}
    assert sorted(n["soprannome"] for n in notifiche.inviate) == ["abe", "emi", "sem"]
    di_nuovo = client.post("/api/giro", headers=con(persone, "abe")).json()
    assert di_nuovo["nuovo"] is False
    assert len(notifiche.inviate) == 3


def test_caricare_una_foto(client, persone, telegram):
    giro_id = apri(client, persone)
    dati = jpeg()
    risposta = client.put(f"/api/giro/{giro_id}/foto", content=dati, headers=con(persone, "emi"))
    assert risposta.status_code == 200
    assert risposta.json() == {"sha256": foto.impronta(dati), "byte": len(dati), "stato": "in_attesa", "versione": 1}
    [inviata] = telegram.di_tipo("manda_foto")
    assert inviata["dati"] == dati


def test_la_foto_di_alberto_non_si_annuncia(client, persone, telegram):
    giro_id = apri(client, persone)
    risposta = client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "abe"))
    assert risposta.json()["stato"] == "accettata"
    assert telegram.di_tipo("manda_foto") == []


def test_foto_rifiutate(client, persone, orologio):
    giro_id = apri(client, persone)
    emi = con(persone, "emi")
    troppo = client.put(
        f"/api/giro/{giro_id}/foto", content=b"x", headers={**emi, "Content-Length": str(foto.MASSIMO + 1)}
    )
    assert troppo.status_code == 413
    assert client.put(f"/api/giro/{giro_id}/foto", content=png(), headers=emi).status_code == 415
    assert client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "abe")).status_code == 200
    doppia = client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "abe"))
    assert doppia.status_code == 409
    assert "definitiva" in doppia.json()["errore"]
    assert client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "ctc")).status_code == 404
    orologio.avanza(hours=48)
    assert client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=emi).status_code == 410


def test_un_corpo_oltre_il_limite_senza_content_length(client, persone):
    giro_id = apri(client, persone)

    def a_pezzi():
        pezzo = b"\xff" * (1024 * 1024)
        for _ in range(9):
            yield pezzo

    risposta = client.put(f"/api/giro/{giro_id}/foto", content=a_pezzi(), headers=con(persone, "emi"))
    assert risposta.status_code == 413


def test_salta(client, persone):
    giro_id = apri(client, persone)
    risposta = client.post(f"/api/giro/{giro_id}/rinvio", headers=con(persone, "emi"))
    assert risposta.status_code == 200
    assert "fino_a" in risposta.json()


def test_iscrizione_push(client, persone, store):
    emi = con(persone, "emi")
    iscrizione = {"endpoint": "https://push.example/1", "keys": {"p256dh": "p", "auth": "a"}}
    assert client.post("/api/push", json=iscrizione, headers=emi).status_code == 204
    assert len(store.iscrizioni_di("emi")) == 1
    assert client.post("/api/push", json={"endpoint": "http://x"}, headers=emi).status_code == 400
    assert client.request("DELETE", "/api/push", json={"endpoint": "https://push.example/1"}, headers=emi).status_code == 204
    assert store.iscrizioni_di("emi") == []


def test_il_lato_di_ctc(client, persone, notifiche, orologio):
    giro_id = apri(client, persone)
    dati = jpeg()
    client.put(f"/api/giro/{giro_id}/foto", content=dati, headers=con(persone, "emi"))
    ctc = con(persone, "ctc")

    giri = client.get("/api/giri", params={"dal": orologio.adesso.isoformat()}, headers=ctc)
    assert [g["id"] for g in giri.json()] == [giro_id]
    assert client.get("/api/giri", params={"dal": "2026-10-04T19:30:00"}, headers=ctc).status_code == 400

    assert client.post(f"/api/giro/{giro_id}/lega", json={"sessione": "2026-10-04"}, headers=ctc).status_code == 200
    assert client.post(f"/api/giro/{giro_id}/lega", json={"sessione": "2026-10-11"}, headers=ctc).status_code == 409

    [elenco] = client.get(f"/api/giro/{giro_id}/foto", headers=ctc).json()
    assert (elenco["soprannome"], elenco["versione"], elenco["stato"]) == ("emi", 1, "in_attesa")
    scaricata = client.get(f"/api/giro/{giro_id}/foto/emi", headers=ctc)
    assert scaricata.content == dati
    assert scaricata.headers["content-type"] == "image/jpeg"

    senza_versione = client.post(f"/api/giro/{giro_id}/foto/emi/esito", json={"esito": "accettata"}, headers=ctc)
    assert senza_versione.status_code == 400
    esito = client.post(
        f"/api/giro/{giro_id}/foto/emi/esito", json={"esito": "da_rifare", "motivo": "sfocata", "versione": 1}, headers=ctc
    )
    assert esito.json() == {"stato": "da_rifare", "motivo": "sfocata", "versione": 1}
    assert notifiche.inviate[-1]["testo"] == "Alberto chiede un'altra foto: sfocata"

    assert [p["soprannome"] for p in client.get("/api/persone", headers=ctc).json()] == ["abe", "emi", "gio", "sem"]


def test_un_giocatore_non_usa_le_rotte_di_ctc(client, persone):
    giro_id = apri(client, persone)
    emi = con(persone, "emi")
    assert client.get("/api/persone", headers=emi).status_code == 404
    assert client.get(f"/api/giro/{giro_id}/foto", headers=emi).status_code == 404


def test_costruisci_dall_ambiente_e_zittisce_httpx(tmp_path, monkeypatch):
    chiave = Vapid()
    chiave.generate_keys()
    pem = tmp_path / "vapid.pem"
    pem.write_bytes(chiave.private_pem())
    ambiente = {
        "RSM_DB": str(tmp_path / "rsm.sqlite"),
        "RSM_FOTO": str(tmp_path / "foto"),
        "RSM_BOT_TOKEN": "123:abc",
        "RSM_GRUPPO_PROVA": "-4000",
        "RSM_ADMIN_TELEGRAM_ID": "123456789",
        "RSM_VAPID_PEM": str(pem),
        "RSM_VAPID_CONTATTO": "mailto:prova@example.org",
    }
    logging.getLogger("httpx").setLevel(logging.INFO)
    app = costruisci(ambiente, avvia_cicli=False)
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert TestClient(app).get("/salute").json() == {"ok": True}
    assert (tmp_path / "foto").is_dir()
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_app.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.app'`.

- [ ] **Step 3: scrivi le rotte**

`src/rsm/app.py`:

```python
"""Le rotte HTTP. Sottili: autenticano, chiamano il servizio, traducono.

Un gettone assente, sconosciuto o con il ruolo sbagliato riceve 404, come una
pagina che non esiste. Ciò che non serve alla risposta (push, messaggi del bot)
va nei `BackgroundTasks`, che girano dopo che la risposta è partita: la pagina
non aspetta Telegram, e `ctc` non va in timeout per colpa sua.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import foto, regole
from .servizio import ErroreServizio, Servizio
from .store import Persona

CSP = (
    "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
    "connect-src 'self'; script-src 'self'; style-src 'self'; manifest-src 'self'; "
    "worker-src 'self'; base-uri 'none'; frame-ancestors 'none'"
)


def crea_app(servizio: Servizio, *, cartella_web: Path, lifespan=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=cartella_web / "static"), name="static")

    @app.exception_handler(ErroreServizio)
    async def _errore_servizio(_richiesta: Request, errore: ErroreServizio) -> JSONResponse:
        return JSONResponse({"errore": str(errore)}, status_code=errore.codice)

    @app.exception_handler(foto.FotoRifiutata)
    async def _foto_rifiutata(_richiesta: Request, errore: foto.FotoRifiutata) -> JSONResponse:
        return JSONResponse({"errore": str(errore)}, status_code=errore.codice)

    def persona_dal_gettone(gettone: str) -> Persona:
        persona = servizio.persona(gettone)
        if persona is None:
            raise HTTPException(status_code=404)
        return persona

    def persona_richiesta(authorization: str | None = Header(default=None)) -> Persona:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=404)
        return persona_dal_gettone(authorization.removeprefix("Bearer ").strip())

    def ruoli(*ammessi: str):
        def dipendenza(persona: Persona = Depends(persona_richiesta)) -> Persona:
            if persona.ruolo not in ammessi:
                raise HTTPException(status_code=404)
            return persona

        return dipendenza

    chi_scatta = ruoli(*regole.CHI_SCATTA)
    chi_apre = ruoli(*regole.CHI_APRE)
    solo_ctc = ruoli(regole.CTC)

    @app.get("/salute")
    def salute() -> dict:
        return {"ok": True}

    # --- la pagina personale

    @app.get("/p/{gettone}")
    def pagina_senza_barra(gettone: str) -> RedirectResponse:
        persona_dal_gettone(gettone)
        return RedirectResponse(f"/p/{gettone}/", status_code=308)

    @app.get("/p/{gettone}/")
    def pagina(gettone: str) -> FileResponse:
        if persona_dal_gettone(gettone).ruolo == regole.CTC:
            raise HTTPException(status_code=404)
        return FileResponse(
            cartella_web / "index.html",
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": CSP,
            },
        )

    @app.get("/p/{gettone}/manifest.webmanifest")
    def manifest(gettone: str) -> JSONResponse:
        persona_dal_gettone(gettone)
        base = f"/p/{gettone}/"
        return JSONResponse(
            {
                "name": "Radiant Selfie Machine",
                "short_name": "Selfie",
                "start_url": base,
                "scope": base,
                "display": "standalone",
                "background_color": "#1b1030",
                "theme_color": "#2b1a4a",
                "icons": [
                    {"src": "/static/icona-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icona-512.png", "sizes": "512x512", "type": "image/png"},
                ],
            },
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/p/{gettone}/sw.js")
    def service_worker(gettone: str) -> FileResponse:
        persona_dal_gettone(gettone)
        return FileResponse(
            cartella_web / "sw.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    # --- la pagina

    @app.get("/api/stato")
    def stato(persona: Persona = Depends(persona_richiesta)) -> dict:
        return servizio.stato(persona)

    @app.post("/api/giro")
    def apri_giro(background: BackgroundTasks, persona: Persona = Depends(chi_apre)) -> dict:
        risposta = servizio.apri_giro(persona)
        if risposta["nuovo"]:
            background.add_task(servizio.invita, persona.soprannome)
        return risposta

    @app.put("/api/giro/{giro_id}/foto")
    async def carica_foto(
        giro_id: int,
        richiesta: Request,
        background: BackgroundTasks,
        persona: Persona = Depends(chi_scatta),
    ) -> dict:
        dichiarati = richiesta.headers.get("content-length", "")
        if dichiarati.isdigit() and int(dichiarati) > foto.MASSIMO:
            raise foto.FotoTroppoGrande(f"la foto supera gli {foto.MASSIMO} byte")
        dati = bytearray()
        async for pezzo in richiesta.stream():
            dati.extend(pezzo)
            if len(dati) > foto.MASSIMO:
                raise foto.FotoTroppoGrande(f"la foto supera gli {foto.MASSIMO} byte")
        ricevuta = await run_in_threadpool(servizio.ricevi_foto, persona, giro_id, bytes(dati))
        if ricevuta.foto.stato == regole.IN_ATTESA:
            background.add_task(
                servizio.annuncia_foto,
                giro_id,
                persona.soprannome,
                ricevuta.foto.versione,
                ricevuta.messaggio_da_ritirare,
            )
        return {
            "sha256": ricevuta.foto.sha256,
            "byte": ricevuta.foto.byte,
            "stato": ricevuta.foto.stato,
            "versione": ricevuta.foto.versione,
        }

    @app.post("/api/giro/{giro_id}/rinvio")
    def rinvia(giro_id: int, persona: Persona = Depends(chi_scatta)) -> dict:
        return {"fino_a": servizio.rinvia(persona, giro_id).isoformat()}

    @app.post("/api/push", status_code=204)
    def iscrivi(dati: dict = Body(...), persona: Persona = Depends(chi_scatta)) -> Response:
        servizio.iscrivi(persona, dati)
        return Response(status_code=204)

    @app.delete("/api/push", status_code=204)
    def disiscrivi(dati: dict = Body(...), persona: Persona = Depends(chi_scatta)) -> Response:
        servizio.disiscrivi(persona, str(dati.get("endpoint", "")))
        return Response(status_code=204)

    # --- ctc

    @app.get("/api/giri")
    def giri(dal: datetime, _ctc: Persona = Depends(solo_ctc)) -> list[dict]:
        # «dal» arriva nella query: il «+» del fuso va codificato (%2B), e httpx
        # lo fa da solo con `params=`. Una data senza fuso è ambigua: 400.
        if dal.tzinfo is None:
            raise HTTPException(status_code=400, detail="«dal» deve avere il fuso orario")
        return servizio.giri_dal(dal)

    @app.post("/api/giro/{giro_id}/lega")
    def lega(giro_id: int, dati: dict = Body(...), _ctc: Persona = Depends(solo_ctc)) -> dict:
        return servizio.lega(giro_id, str(dati.get("sessione", "")))

    @app.get("/api/giro/{giro_id}/foto")
    def elenco_foto(giro_id: int, _ctc: Persona = Depends(solo_ctc)) -> list[dict]:
        return servizio.foto_del_giro(giro_id)

    @app.get("/api/giro/{giro_id}/foto/{soprannome}")
    def scarica_foto(giro_id: int, soprannome: str, _ctc: Persona = Depends(solo_ctc)) -> Response:
        return Response(
            servizio.dati_foto(giro_id, soprannome),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/giro/{giro_id}/foto/{soprannome}/esito")
    def esito(
        giro_id: int,
        soprannome: str,
        background: BackgroundTasks,
        dati: dict = Body(...),
        _ctc: Persona = Depends(solo_ctc),
    ) -> dict:
        versione = dati.get("versione")
        if not isinstance(versione, int) or isinstance(versione, bool):
            raise HTTPException(status_code=400, detail="«versione» mancante")
        motivo = dati.get("motivo")
        if motivo is not None and not isinstance(motivo, str):
            raise HTTPException(status_code=400, detail="«motivo» deve essere un testo")
        decisa = servizio.decidi(giro_id, soprannome, versione, str(dati.get("esito", "")), motivo)
        background.add_task(servizio.dopo_decisione, decisa)
        return {"stato": decisa.stato, "motivo": decisa.motivo, "versione": decisa.versione}

    @app.get("/api/persone")
    def persone(_ctc: Persona = Depends(solo_ctc)) -> list[dict]:
        return servizio.persone()

    return app
```

`src/rsm/principale.py`:

```python
"""Il punto d'ingresso: costruisce il servizio vero dall'ambiente.

    uvicorn --factory rsm.principale:costruisci --no-access-log

Il log d'accesso di uvicorn resta spento: scriverebbe il percorso di ogni
richiesta, e il percorso della pagina contiene il gettone. Il logger `httpx`
sta a WARNING per lo stesso motivo: al livello INFO scriverebbe l'URL di ogni
chiamata a Telegram, token compreso.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from py_vapid import Vapid

from . import cicli, config
from .app import crea_app
from .push import Notificatore, chiave_pubblica
from .servizio import Servizio
from .store import Store
from .telegram import BotTelegram
from .validazione import Validatore

CARTELLA_WEB = Path(__file__).resolve().parents[2] / "web"


def costruisci(env: Mapping[str, str] | None = None, *, avvia_cicli: bool = True) -> FastAPI:
    env = os.environ if env is None else env
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    imp = config.da_ambiente(env)
    imp.cartella_foto.mkdir(parents=True, exist_ok=True)
    store = Store(imp.db)
    store.crea_schema()
    vapid = Vapid.from_file(str(imp.vapid_pem))
    telegram = BotTelegram(imp.token_bot)
    servizio = Servizio(
        store=store,
        cartella_foto=imp.cartella_foto,
        telegram=telegram,
        notifiche=Notificatore(store, vapid, imp.vapid_contatto),
        impostazioni=imp,
        chiave_vapid=chiave_pubblica(vapid),
    )
    validatore = Validatore(servizio, telegram, imp.admin_telegram_id, imp.motivi)

    lifespan = None
    if avvia_cicli:

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            fermo = threading.Event()
            fili = [
                threading.Thread(
                    target=cicli.ciclo_bot,
                    args=(telegram, validatore, store, fermo),
                    name="bot",
                    daemon=True,
                ),
                threading.Thread(
                    target=cicli.ciclo_pianificatore,
                    args=(servizio, fermo),
                    name="pianificatore",
                    daemon=True,
                ),
            ]
            for filo in fili:
                filo.start()
            try:
                yield
            finally:
                fermo.set()

    cartella_web = Path(env.get("RSM_WEB") or CARTELLA_WEB)
    return crea_app(servizio, cartella_web=cartella_web, lifespan=lifespan)
```

Nota: `costruisci` monta `/static` da `cartella_web / "static"`; nel test la cartella `web/static` del repository non esiste ancora (arriva nel Task 15). Per questo lo step 4 crea subito la cartella con un segnaposto.

- [ ] **Step 4: crea la cartella della pagina con un segnaposto**

```bash
mkdir -p web/static
touch web/static/.gitkeep
```

- [ ] **Step 5: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 6: prova a mano l'avvio vero, in locale**

```bash
mkdir -p dati/prova
uv run rsm vapid genera dati/prova/vapid.pem
RSM_DB=dati/prova/rsm.sqlite RSM_FOTO=dati/prova/foto RSM_BOT_TOKEN=123:finto \
RSM_GRUPPO_PROVA=-1 RSM_ADMIN_TELEGRAM_ID=1 RSM_VAPID_PEM=dati/prova/vapid.pem \
RSM_VAPID_CONTATTO=mailto:prova@example.org \
uv run uvicorn --factory rsm.principale:costruisci --port 8471 --no-access-log
```

In un altro terminale: `curl -s http://127.0.0.1:8471/salute`
Expected: `{"ok":true}`. Nel log del servizio compaiono avvisi «lettura del bot non riuscita: getUpdates: Unauthorized» (il token è finto): nessun token nel testo. Ferma con Ctrl-C e `rm -rf dati/prova` (`dati/` è ignorata da git). Questo passo usa `rsm vapid genera`, che arriva nel Task 13: se esegui i task in ordine, fai questa prova alla fine del Task 13.

- [ ] **Step 7: commit**

```bash
git add src/rsm/app.py src/rsm/principale.py tests/test_app.py web/static/.gitkeep
git commit -m "HTTP routes and entry point; httpx logger silenced

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: la riga di comando

`rsm persona aggiungi|revoca|rimuovi|elenco` e `rsm vapid genera`, da lanciare dentro il container. Il link si stampa una volta sola; il gettone di `ctc` si stampa nudo, perché va nel portachiavi del Mac. La chiave VAPID nasce con i permessi 600, senza un istante con permessi più larghi.

**Files:**
- Create: `src/rsm/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `config.percorso_db`, `config.url_base`, `ConfigurazioneErrata` (Task 6); `gettoni` (Task 2); `regole.RUOLI`, `regole.CTC`, `regole.soprannome_valido`, `RegolaViolata` (Task 1); `Store` (Task 3); `chiave_pubblica` (Task 5).
- Produces (`rsm.cli`): `main(argv: list[str] | None = None, *, env: Mapping[str, str] | None = None, stampa=print) -> int` (0 riuscito, 1 rifiutato, 2 configurazione o argomento non valido). Il comando `rsm` è già dichiarato in `pyproject.toml`.

- [ ] **Step 1: scrivi i test**

`tests/test_cli.py`:

```python
import base64
import os
import stat

from rsm import gettoni
from rsm.cli import main
from rsm.store import Store


def ambiente(tmp_path):
    return {"RSM_DB": str(tmp_path / "rsm.sqlite"), "RSM_URL_BASE": "https://selfie.example.org"}


def esegui(argomenti, env):
    righe = []
    codice = main(argomenti, env=env, stampa=righe.append)
    return codice, "\n".join(righe)


def gettone_dal_link(uscita):
    return uscita.strip().splitlines()[-1].removeprefix("https://selfie.example.org/p/").rstrip("/")


def test_aggiungere_stampa_il_link_una_volta(tmp_path):
    env = ambiente(tmp_path)
    codice, uscita = esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    assert codice == 0
    assert "https://selfie.example.org/p/" in uscita
    persona = Store(env["RSM_DB"]).persona_da_impronta(gettoni.impronta(gettone_dal_link(uscita)))
    assert (persona.soprannome, persona.ruolo) == ("emi", "giocatore")


def test_una_persona_non_si_aggiunge_due_volte(tmp_path):
    env = ambiente(tmp_path)
    esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    codice, uscita = esegui(["persona", "aggiungi", "emi", "--ruolo", "master"], env)
    assert codice == 1
    assert "esiste già" in uscita


def test_il_gettone_di_ctc_si_stampa_nudo(tmp_path):
    env = ambiente(tmp_path)
    codice, uscita = esegui(["persona", "aggiungi", "ctc", "--ruolo", "ctc"], env)
    assert codice == 0
    gettone = uscita.strip().splitlines()[-1]
    assert "http" not in gettone
    assert Store(env["RSM_DB"]).persona_da_impronta(gettoni.impronta(gettone)).ruolo == "ctc"


def test_revocare_cambia_il_link(tmp_path):
    env = ambiente(tmp_path)
    _, prima = esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], env)
    codice, dopo = esegui(["persona", "revoca", "emi"], env)
    assert codice == 0
    store = Store(env["RSM_DB"])
    assert store.persona_da_impronta(gettoni.impronta(gettone_dal_link(prima))) is None
    assert store.persona_da_impronta(gettoni.impronta(gettone_dal_link(dopo))).soprannome == "emi"
    assert esegui(["persona", "revoca", "nessuno"], env)[0] == 1


def test_rimuovere_ed_elencare(tmp_path):
    env = ambiente(tmp_path)
    esegui(["persona", "aggiungi", "gio", "--ruolo", "master"], env)
    esegui(["persona", "aggiungi", "prova", "--ruolo", "giocatore"], env)
    assert esegui(["persona", "rimuovi", "prova"], env)[0] == 0
    assert esegui(["persona", "rimuovi", "prova"], env)[0] == 1
    codice, uscita = esegui(["persona", "elenco"], env)
    assert codice == 0
    assert uscita == "gio  master"


def test_elenco_vuoto(tmp_path):
    assert esegui(["persona", "elenco"], ambiente(tmp_path)) == (0, "nessuna persona")


def test_errori_di_configurazione_e_di_argomenti(tmp_path):
    assert esegui(["persona", "aggiungi", "Emi!", "--ruolo", "giocatore"], ambiente(tmp_path))[0] == 2
    assert esegui(["persona", "elenco"], {})[0] == 2
    senza_base = {"RSM_DB": str(tmp_path / "rsm.sqlite")}
    codice, uscita = esegui(["persona", "aggiungi", "emi", "--ruolo", "giocatore"], senza_base)
    assert codice == 2 and "RSM_URL_BASE" in uscita
    assert Store(senza_base["RSM_DB"]).persone() == []  # niente persona senza link da consegnare


def test_vapid_genera_una_chiave_privata_leggibile_solo_dal_proprietario(tmp_path):
    percorso = tmp_path / "vapid.pem"
    codice, uscita = esegui(["vapid", "genera", str(percorso)], {})
    assert codice == 0
    assert stat.S_IMODE(os.stat(percorso).st_mode) == 0o600
    assert percorso.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    chiave = uscita.strip().splitlines()[-1]
    assert len(base64.urlsafe_b64decode(chiave + "=")) == 65


def test_vapid_non_sovrascrive(tmp_path):
    percorso = tmp_path / "vapid.pem"
    percorso.write_text("già qui")
    codice, uscita = esegui(["vapid", "genera", str(percorso)], {})
    assert codice == 1
    assert "non sovrascrivo" in uscita
    assert percorso.read_text() == "già qui"
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'rsm.cli'`.

- [ ] **Step 3: scrivi la riga di comando**

`src/rsm/cli.py`:

```python
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
    revoca = azioni.add_parser("revoca", help="annulla il link e ne stampa uno nuovo")
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
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: tutta la suite veloce PASS.

- [ ] **Step 5: commit**

```bash
git add src/rsm/cli.py tests/test_cli.py
git commit -m "rsm CLI: people, one-time links, VAPID key created 0600

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 14: la macchina a stati della pagina

Il cuore della pagina, senza browser: cosa mostrare, dato lo stato del servizio e quello che la persona sta facendo adesso; come avanza la fase locale; i tentativi di invio; qualche conversione. Si prova con `node --test`, senza dipendenze.

**Files:**
- Create: `web/package.json`, `web/static/stati.js`
- Test: `web/test/stati.test.js`

**Interfaces:**
- Consumes: la forma di `/api/stato` (Task 7) e di `POST /api/giro` (Task 12).
- Produces (modulo ES `web/static/stati.js`): `FASE_INIZIALE = { fase: 'riposo' }`; `dopo(locale, evento) -> { fase }` (eventi: `scatta`, `scattata`, `negata`, `annulla`, `rifai`, `invia`, `inviata`, `fallita`, `respinta`, `riprova`, `lascia_perdere`; un evento non ammesso solleva `Error`); `schermata(server, locale, oraMs) -> { nome, motivo? }` con `nome` fra `caricamento`, `nessun_giro`, `invito`, `rinviato`, `nuova_richiesta`, `anteprima`, `revisione`, `invio`, `errore_invio`, `in_attesa`, `accettata`, `fotocamera_negata`; `msAllaFineDelRinvio(server, oraMs) -> number | null`; `conTentativi(operazione, tentativi = 3, attendi) -> Promise` (non ritenta un errore con `definitivo: true`); `ETICHETTE_PANNELLO`; `esitoApertura(risposta, formattaOra) -> string`; `base64UrlInByte(testo) -> Uint8Array`; `esadecimale(buffer) -> string`.

- [ ] **Step 1: scrivi i test**

`web/package.json`:

```json
{
  "private": true,
  "type": "module"
}
```

`web/test/stati.test.js`:

```js
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  FASE_INIZIALE,
  base64UrlInByte,
  conTentativi,
  dopo,
  esadecimale,
  esitoApertura,
  msAllaFineDelRinvio,
  schermata,
} from '../static/stati.js';

const ORA = Date.parse('2026-10-04T20:00:00Z');
const GIRO = { id: 1, aperto_alle: '2026-10-04T19:30:00+00:00', scade_alle: '2026-10-06T19:30:00+00:00' };
const stato = (altro = {}) => ({
  persona: 'emi', ruolo: 'giocatore', giro: GIRO, foto: null, rinvio_fino_a: null, ...altro,
});
const in_fase = (fase) => ({ fase });

test('prima della prima risposta si aspetta', () => {
  assert.equal(schermata(null, FASE_INIZIALE, ORA).nome, 'caricamento');
});

test('senza giro la fotocamera resta spenta', () => {
  assert.equal(schermata(stato({ giro: null }), FASE_INIZIALE, ORA).nome, 'nessun_giro');
});

test('con un giro e senza foto si invita', () => {
  assert.equal(schermata(stato(), FASE_INIZIALE, ORA).nome, 'invito');
});

test('una foto accettata vince anche sulla fase locale', () => {
  const s = stato({ foto: { stato: 'accettata', sha256: 'x', motivo: null } });
  assert.equal(schermata(s, in_fase('anteprima'), ORA).nome, 'accettata');
});

test('la fase locale vince sullo stato del servizio', () => {
  const s = stato({ foto: { stato: 'in_attesa', sha256: 'x', motivo: null } });
  for (const fase of ['anteprima', 'revisione', 'invio', 'errore_invio', 'fotocamera_negata']) {
    assert.equal(schermata(s, in_fase(fase), ORA).nome, fase);
  }
});

test('una foto in attesa', () => {
  const s = stato({ foto: { stato: 'in_attesa', sha256: 'x', motivo: null } });
  assert.equal(schermata(s, FASE_INIZIALE, ORA).nome, 'in_attesa');
});

test('il rinvio vale finché non scade, sull\'ora data', () => {
  const s = stato({ rinvio_fino_a: '2026-10-04T20:10:00+00:00' });
  assert.equal(schermata(s, FASE_INIZIALE, ORA).nome, 'rinviato');
  assert.equal(schermata(s, FASE_INIZIALE, Date.parse('2026-10-04T20:10:00Z')).nome, 'invito');
});

test('la richiesta di un\'altra foto porta il motivo, se c\'è', () => {
  const con = stato({ foto: { stato: 'da_rifare', sha256: 'x', motivo: 'troppo buia' } });
  assert.deepEqual(schermata(con, FASE_INIZIALE, ORA), { nome: 'nuova_richiesta', motivo: 'troppo buia' });
  const senza = stato({ foto: { stato: 'da_rifare', sha256: 'x', motivo: null } });
  assert.deepEqual(schermata(senza, FASE_INIZIALE, ORA), { nome: 'nuova_richiesta', motivo: null });
});

test('le transizioni di uno scatto, con un invio fallito e ritentato', () => {
  let locale = FASE_INIZIALE;
  for (const [evento, attesa] of [
    ['scatta', 'anteprima'], ['scattata', 'revisione'], ['rifai', 'anteprima'],
    ['scattata', 'revisione'], ['invia', 'invio'], ['fallita', 'errore_invio'],
    ['riprova', 'invio'], ['inviata', 'riposo'],
  ]) {
    locale = dopo(locale, evento);
    assert.equal(locale.fase, attesa, `dopo «${evento}»`);
  }
});

test('le uscite laterali', () => {
  assert.equal(dopo(in_fase('anteprima'), 'negata').fase, 'fotocamera_negata');
  assert.equal(dopo(in_fase('fotocamera_negata'), 'riprova').fase, 'anteprima');
  assert.equal(dopo(in_fase('invio'), 'respinta').fase, 'riposo');
  assert.equal(dopo(in_fase('errore_invio'), 'lascia_perdere').fase, 'riposo');
  assert.equal(dopo(in_fase('anteprima'), 'annulla').fase, 'riposo');
});

test('un evento fuori posto è rifiutato', () => {
  assert.throws(() => dopo(FASE_INIZIALE, 'invia'), /non ammesso/);
});

test('conTentativi riprova tre volte e poi rinuncia', async () => {
  let volte = 0;
  const attese = [];
  await assert.rejects(
    conTentativi(async () => { volte += 1; throw new Error('rete'); }, 3, async (ms) => { attese.push(ms); }),
    /rete/,
  );
  assert.equal(volte, 3);
  assert.deepEqual(attese, [1000, 2000]);
});

test('conTentativi non ritenta un errore definitivo', async () => {
  let volte = 0;
  const definitivo = Object.assign(new Error('409'), { definitivo: true });
  await assert.rejects(conTentativi(async () => { volte += 1; throw definitivo; }, 3, async () => {}));
  assert.equal(volte, 1);
});

test('conTentativi si ferma al primo successo', async () => {
  let volte = 0;
  const risultato = await conTentativi(async () => {
    volte += 1;
    if (volte < 2) throw new Error('rete');
    return 'ok';
  }, 3, async () => {});
  assert.equal(risultato, 'ok');
  assert.equal(volte, 2);
});

test('il messaggio dopo «Apri il giro» dice la verità', () => {
  const ora = () => '22:10';
  assert.equal(esitoApertura({ nuovo: false, giro: GIRO, annuncio: null }, ora), 'Giro già aperto alle 22:10.');
  assert.equal(
    esitoApertura({ nuovo: true, giro: GIRO, annuncio: { esito: 'fallito', gruppo: 'party' } }, ora),
    'Giro aperto, ma il messaggio nel gruppo non è partito.',
  );
  assert.equal(
    esitoApertura({ nuovo: true, giro: GIRO, annuncio: { esito: 'inviato', gruppo: 'prova' } }, ora),
    'Giro aperto. Annuncio mandato nel gruppo di prova: la sicura è inserita.',
  );
  assert.equal(
    esitoApertura({ nuovo: true, giro: GIRO, annuncio: { esito: 'inviato', gruppo: 'party' } }, ora),
    'Giro aperto. Annuncio mandato nel gruppo del party.',
  );
});

test('msAllaFineDelRinvio', () => {
  assert.equal(msAllaFineDelRinvio(null, ORA), null);
  assert.equal(msAllaFineDelRinvio(stato(), ORA), null);
  assert.equal(msAllaFineDelRinvio(stato({ rinvio_fino_a: '2026-10-04T20:00:05+00:00' }), ORA), 5000);
  assert.equal(msAllaFineDelRinvio(stato({ rinvio_fino_a: '2026-10-04T19:59:59+00:00' }), ORA), null);
});

test('base64url in byte, con e senza padding', () => {
  assert.deepEqual([...base64UrlInByte('AQID')], [1, 2, 3]);
  assert.deepEqual([...base64UrlInByte('-_8')], [251, 255]);
});

test('esadecimale', () => {
  assert.equal(esadecimale(new Uint8Array([0, 15, 255]).buffer), '000fff');
});
```

- [ ] **Step 2: lancia i test e verifica che falliscano**

Run: `node --test "web/test/*.test.js"`
Expected: FAIL, `Cannot find module '…/web/static/stati.js'`.

- [ ] **Step 3: scrivi la macchina a stati**

`web/static/stati.js`:

```js
// La macchina a stati della pagina. Non tocca il browser: si prova con
//   node --test "web/test/*.test.js"
//
// `schermata` decide cosa mostrare a partire dallo stato del servizio e dalla
// fase locale (quello che la persona sta facendo adesso); `dopo` fa avanzare la
// fase locale e rifiuta un evento che in quella fase non ha senso.

export const FASE_INIZIALE = Object.freeze({ fase: 'riposo' });

const TRANSIZIONI = {
  riposo: { scatta: 'anteprima' },
  anteprima: { scattata: 'revisione', negata: 'fotocamera_negata', annulla: 'riposo' },
  revisione: { rifai: 'anteprima', invia: 'invio' },
  invio: { inviata: 'riposo', fallita: 'errore_invio', respinta: 'riposo' },
  errore_invio: { riprova: 'invio', lascia_perdere: 'riposo' },
  fotocamera_negata: { riprova: 'anteprima', annulla: 'riposo' },
};

const FASI_CHE_VINCONO = new Set(['anteprima', 'revisione', 'invio', 'errore_invio', 'fotocamera_negata']);

export function dopo(locale, evento) {
  const prossima = TRANSIZIONI[locale.fase]?.[evento];
  if (!prossima) throw new Error(`evento «${evento}» non ammesso nella fase «${locale.fase}»`);
  return { fase: prossima };
}

export function msAllaFineDelRinvio(server, oraMs) {
  if (!server?.rinvio_fino_a) return null;
  const resto = Date.parse(server.rinvio_fino_a) - oraMs;
  return resto > 0 ? resto : null;
}

export function schermata(server, locale, oraMs) {
  if (!server) return { nome: 'caricamento' };
  if (!server.giro) return { nome: 'nessun_giro' };
  const foto = server.foto;
  if (foto?.stato === 'accettata') return { nome: 'accettata' };
  if (FASI_CHE_VINCONO.has(locale.fase)) return { nome: locale.fase };
  if (foto?.stato === 'in_attesa') return { nome: 'in_attesa' };
  if (msAllaFineDelRinvio(server, oraMs) !== null) return { nome: 'rinviato' };
  if (foto?.stato === 'da_rifare') return { nome: 'nuova_richiesta', motivo: foto.motivo ?? null };
  return { nome: 'invito' };
}

// Ritenta un'operazione che fallisce per la rete o per il servizio (5xx), con
// attese di 1 s e 2 s. Un errore definitivo (un 4xx: la foto è già accettata,
// il giro è chiuso) non si ritenta: rifarlo darebbe lo stesso no.
export async function conTentativi(
  operazione,
  tentativi = 3,
  attendi = (ms) => new Promise((risolvi) => setTimeout(risolvi, ms)),
) {
  let ultimo;
  for (let i = 0; i < tentativi; i += 1) {
    try {
      return await operazione();
    } catch (errore) {
      if (errore?.definitivo) throw errore;
      ultimo = errore;
      if (i < tentativi - 1) await attendi(1000 * 2 ** i);
    }
  }
  throw ultimo;
}

export const ETICHETTE_PANNELLO = Object.freeze({
  nessuna: 'nessuna foto',
  rinviato: 'ha rimandato',
  in_attesa: 'in attesa di validazione',
  accettata: 'accettata',
  da_rifare: 'deve rifarla',
});

export function esitoApertura(risposta, formattaOra) {
  if (!risposta.nuovo) return `Giro già aperto alle ${formattaOra(risposta.giro.aperto_alle)}.`;
  if (risposta.annuncio?.esito === 'fallito') {
    return 'Giro aperto, ma il messaggio nel gruppo non è partito.';
  }
  if (risposta.annuncio?.gruppo === 'prova') {
    return 'Giro aperto. Annuncio mandato nel gruppo di prova: la sicura è inserita.';
  }
  return 'Giro aperto. Annuncio mandato nel gruppo del party.';
}

export function base64UrlInByte(testo) {
  const base64 = testo.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (testo.length % 4)) % 4);
  return Uint8Array.from(atob(base64), (carattere) => carattere.charCodeAt(0));
}

export function esadecimale(buffer) {
  return Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, '0')).join('');
}
```

- [ ] **Step 4: lancia i test e verifica che passino**

Run: `node --test "web/test/*.test.js"`
Expected: tutti `ok`, `# fail 0`.

- [ ] **Step 5: commit**

```bash
git add web/package.json web/static/stati.js web/test/stati.test.js
git commit -m "page state machine with node tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: la pagina, il service worker, le icone, le prove in Chrome

La pagina vera: HTML, CSS e il modulo che collega `stati.js` al browser (fotocamera, scatto su canvas, invio con verifica dell'impronta, polling, notifiche, pannello). Il service worker mostra i push e al tocco apre la pagina personale. Tre prove da capo a fondo in Chrome con la webcam finta verificano che tutto questo stia insieme.

**Files:**
- Create: `web/index.html`, `web/static/stile.css`, `web/static/app.js`, `web/sw.js`, `strumenti/icone.py`, `web/static/icona-192.png`, `web/static/icona-512.png`
- Delete: `web/static/.gitkeep`
- Test: `tests/e2e/__init__.py`, `tests/e2e/conftest.py`, `tests/e2e/test_pagina.py`

**Interfaces:**
- Consumes: tutto `web/static/stati.js` (Task 14); le rotte del Task 12 (`/api/stato`, `/api/giro`, `/api/giro/{id}/foto`, `/api/giro/{id}/rinvio`, `/api/push`, `/p/{gettone}/sw.js`, `/p/{gettone}/manifest.webmanifest`); il carico utile dei push `{"titolo", "testo"}` (Task 5); `crea_app` (Task 12); `Servizio` e i finti (Task 6-7).
- Produces: la pagina. Le sezioni hanno `data-schermata="<nome>"` con i nomi di `schermata()`; i pulsanti hanno gli id `scatta`, `salta`, `scatta-di-nuovo`, `scatta-ora`, `scatta-foto`, `annulla`, `invia`, `rifai`, `riprova`, `lascia-perdere`, `rifai-in-attesa`, `riprova-fotocamera`, `annulla-fotocamera`, `attiva-notifiche`, `apri-giro`. Le prove e2e li usano.

- [ ] **Step 1: scrivi le prove da capo a fondo**

`tests/e2e/__init__.py`: vuoto.

`tests/e2e/conftest.py`:

```python
"""Il servizio vero, con Telegram e push finti, su una porta locale; e Chrome con
la webcam finta. 127.0.0.1 per il browser è un contesto sicuro: fotocamera,
service worker e crypto.subtle funzionano come in HTTPS."""

import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import uvicorn

from rsm import gettoni
from rsm.app import crea_app
from rsm.servizio import Servizio
from rsm.store import Store
from tests.finti import NotificheFinte, TelegramFinto, impostazioni_di_prova

CARTELLA_WEB = Path(__file__).resolve().parents[2] / "web"


def _porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def in_rete(tmp_path):
    imp = impostazioni_di_prova(tmp_path)
    store = Store(imp.db)
    store.crea_schema()
    telegram = TelegramFinto()
    servizio = Servizio(
        store=store, cartella_foto=imp.cartella_foto, telegram=telegram,
        notifiche=NotificheFinte(), impostazioni=imp, chiave_vapid="BAAA",
    )
    gettone_emi, gettone_gio = gettoni.genera(), gettoni.genera()
    store.aggiungi_persona("emi", "giocatore", gettoni.impronta(gettone_emi))
    store.aggiungi_persona("gio", "master", gettoni.impronta(gettone_gio))
    porta = _porta_libera()
    server = uvicorn.Server(
        uvicorn.Config(crea_app(servizio, cartella_web=CARTELLA_WEB), host="127.0.0.1", port=porta, log_level="warning")
    )
    filo = threading.Thread(target=server.run, daemon=True)
    filo.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield SimpleNamespace(
        url=f"http://127.0.0.1:{porta}",
        servizio=servizio,
        store=store,
        telegram=telegram,
        emi=gettone_emi,
        gio=store.persona_da_impronta(gettoni.impronta(gettone_gio)),
    )
    server.should_exit = True
    filo.join(timeout=5)


@pytest.fixture
def pagina():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        )
        yield browser.new_page()
        browser.close()
```

`tests/e2e/test_pagina.py`:

```python
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


def test_salta_rimanda_l_invito(in_rete, pagina):
    in_rete.servizio.apri_giro(in_rete.gio)
    pagina.goto(f"{in_rete.url}/p/{in_rete.emi}/")
    schermata(pagina, "invito").wait_for(state="visible")
    pagina.click("#salta")
    schermata(pagina, "rinviato").wait_for(state="visible")
    giro = in_rete.store.ultimo_giro()
    assert in_rete.store.rinvio(giro.id, "emi") is not None
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest -m e2e -q`
Expected: FAIL: la pagina non esiste ancora (`web/index.html` manca, le attese scadono).

- [ ] **Step 3: scrivi la pagina**

`web/index.html`:

```html
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#2b1a4a">
  <title>Radiant Selfie Machine</title>
  <link rel="manifest" href="manifest.webmanifest">
  <link rel="icon" href="/static/icona-192.png">
  <link rel="apple-touch-icon" href="/static/icona-192.png">
  <link rel="stylesheet" href="/static/stile.css">
  <script type="module" src="/static/app.js"></script>
</head>
<body>
  <main>
    <header>
      <h1>Radiant Selfie Machine</h1>
      <p id="chi"></p>
    </header>

    <section data-schermata="caricamento"><p>Un attimo…</p></section>

    <section data-schermata="nessun_giro" hidden>
      <p class="grande">Nessun giro aperto.</p>
      <p>Quando il master apre il giro dei selfie, l'invito compare qui.</p>
    </section>

    <section data-schermata="invito" hidden>
      <p class="grande">📸 È il momento del selfie per la miniatura!</p>
      <div class="azioni">
        <button id="scatta" class="primario">Scatta</button>
        <button id="salta">Salta</button>
      </div>
    </section>

    <section data-schermata="nuova_richiesta" hidden>
      <p class="grande">Alberto chiede un'altra foto<span id="motivo"></span></p>
      <div class="azioni"><button id="scatta-di-nuovo" class="primario">Scatta</button></div>
    </section>

    <section data-schermata="rinviato" hidden>
      <p class="grande">D'accordo: te lo richiedo tra qualche minuto.</p>
      <div class="azioni"><button id="scatta-ora">Scatta adesso</button></div>
    </section>

    <section data-schermata="anteprima" hidden>
      <video id="video" autoplay playsinline muted></video>
      <div class="azioni">
        <button id="scatta-foto" class="primario">Scatta la foto</button>
        <button id="annulla">Annulla</button>
      </div>
    </section>

    <section data-schermata="revisione" hidden>
      <img id="foto" alt="La foto appena scattata">
      <div class="azioni">
        <button id="invia" class="primario">Invia</button>
        <button id="rifai">Rifai</button>
      </div>
    </section>

    <section data-schermata="invio" hidden><p class="grande">Invio in corso…</p></section>

    <section data-schermata="errore_invio" hidden>
      <p class="grande">Invio non riuscito.</p>
      <p>La foto è ancora qui: puoi riprovare. Se non va, puoi sempre mandarla su Telegram.</p>
      <div class="azioni">
        <button id="riprova" class="primario">Riprova</button>
        <button id="lascia-perdere">Lascia perdere</button>
      </div>
    </section>

    <section data-schermata="in_attesa" hidden>
      <p class="grande">Foto ricevuta.</p>
      <p>Alberto la guarda e ti fa sapere. Finché non ha deciso, puoi ancora rifarla.</p>
      <div class="azioni"><button id="rifai-in-attesa">Rifai</button></div>
    </section>

    <section data-schermata="accettata" hidden>
      <p class="grande">La tua foto è stata accettata. Grazie!</p>
    </section>

    <section data-schermata="fotocamera_negata" hidden>
      <p class="grande">Non riesco ad accendere la fotocamera.</p>
      <p>Controlla che il browser abbia il permesso di usarla (di solito dall'icona accanto all'indirizzo) e che nessun'altra applicazione la stia usando. Se non va, puoi sempre mandare la foto su Telegram.</p>
      <div class="azioni">
        <button id="riprova-fotocamera" class="primario">Riprova</button>
        <button id="annulla-fotocamera">Annulla</button>
      </div>
    </section>

    <p id="avviso" role="status" hidden></p>

    <section id="notifiche" hidden>
      <p id="notifiche-testo">Vuoi ricevere l'invito anche a pagina chiusa?</p>
      <button id="attiva-notifiche">Attiva le notifiche</button>
    </section>
    <p id="suggerimento-ios" hidden>Su iPhone e iPad le notifiche arrivano solo se aggiungi questa pagina alla schermata Home: Condividi → Aggiungi alla schermata Home.</p>

    <section id="pannello" hidden>
      <h2>Il giro</h2>
      <button id="apri-giro" class="primario">Apri il giro</button>
      <p id="esito-giro" role="status"></p>
      <ul id="stati"></ul>
    </section>
  </main>
  <canvas id="tela" hidden></canvas>
</body>
</html>
```

`web/static/stile.css`:

```css
:root {
  color-scheme: dark;
  --fondo: #1b1030;
  --carta: #2b1a4a;
  --testo: #f3eefc;
  --tenue: #b9a9d6;
  --accento: #f2c85a;
  --accento-testo: #1b1030;
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }

body {
  margin: 0;
  min-height: 100vh;
  background: var(--fondo);
  color: var(--testo);
  font: 17px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}

main { max-width: 40rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
header h1 { font-size: 1.3rem; margin: 0; }
header p { margin: 0.25rem 0 1.5rem; color: var(--tenue); }

section { background: var(--carta); border-radius: 1rem; padding: 1.25rem; margin-bottom: 1rem; }
.grande { font-size: 1.25rem; margin-top: 0; }
.azioni { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 1rem; }

button {
  font: inherit;
  color: var(--testo);
  background: transparent;
  border: 1px solid var(--tenue);
  border-radius: 999px;
  padding: 0.6rem 1.2rem;
  cursor: pointer;
}
button.primario { background: var(--accento); border-color: var(--accento); color: var(--accento-testo); font-weight: 600; }
button:disabled { opacity: 0.5; cursor: default; }

/* Anteprima e revisione a specchio, come uno specchio. La foto salvata no:
   come fanno le fotocamere frontali dei telefoni. */
video, #foto { width: 100%; border-radius: 0.75rem; background: #000; transform: scaleX(-1); }

#avviso { color: var(--accento); }
#pannello ul { list-style: none; padding: 0; margin: 1rem 0 0; }
#pannello li { padding: 0.35rem 0; border-top: 1px solid rgba(255, 255, 255, 0.08); }
```

`web/static/app.js`:

```js
// La pagina: collega la macchina a stati (stati.js) al browser.
import {
  ETICHETTE_PANNELLO,
  FASE_INIZIALE,
  base64UrlInByte,
  conTentativi,
  dopo,
  esadecimale,
  esitoApertura,
  msAllaFineDelRinvio,
  schermata,
} from './stati.js';

const gettone = location.pathname.split('/')[2];
const base = `/p/${gettone}/`;
const $ = (id) => document.getElementById(id);

let server = null;
let locale = { ...FASE_INIZIALE };
let scarto = 0; // ora del server meno ora del dispositivo, in millisecondi
let flusso = null;
let accensione = null;
let fotoPronta = null;
let timerRinvio = null;
let registrazione = null;

class ErroreApi extends Error {
  constructor(stato, messaggio) {
    super(messaggio);
    this.stato = stato;
    this.definitivo = stato >= 400 && stato < 500;
  }
}

async function api(metodo, percorso, corpo, tipo) {
  const intestazioni = { Authorization: `Bearer ${gettone}` };
  if (tipo) intestazioni['Content-Type'] = tipo;
  const risposta = await fetch(percorso, { method: metodo, headers: intestazioni, body: corpo, cache: 'no-store' });
  if (!risposta.ok) {
    let messaggio = `HTTP ${risposta.status}`;
    try {
      const dati = await risposta.json();
      messaggio = dati.errore ?? dati.detail ?? messaggio;
    } catch {
      // corpo non JSON: resta il codice HTTP
    }
    throw new ErroreApi(risposta.status, messaggio);
  }
  return risposta.status === 204 ? null : risposta.json();
}

const oraServer = () => Date.now() + scarto;

function avvisa(testo) {
  const elemento = $('avviso');
  elemento.textContent = testo;
  elemento.hidden = !testo;
}

async function aggiorna() {
  try {
    server = await api('GET', '/api/stato');
    scarto = Date.parse(server.ora) - Date.now();
  } catch {
    avvisa('Non riesco a raggiungere il servizio: riprovo tra poco.');
    return;
  }
  disegna();
}

// Un doppio tocco manda lo stesso evento due volte: il secondo non è ammesso
// nella fase nuova, e va semplicemente ignorato.
function vai(evento) {
  try {
    locale = dopo(locale, evento);
  } catch {
    return;
  }
  disegna();
}

function disegna() {
  const vista = schermata(server, locale, oraServer());
  for (const sezione of document.querySelectorAll('[data-schermata]')) {
    sezione.hidden = sezione.dataset.schermata !== vista.nome;
  }
  $('motivo').textContent = vista.motivo ? `: ${vista.motivo}` : '.';
  if (vista.nome === 'anteprima') accendiFotocamera();
  else spegniFotocamera();
  if (server) {
    $('chi').textContent = `Ciao ${server.persona}!`;
    disegnaPannello();
    disegnaNotifiche();
  }
  clearTimeout(timerRinvio);
  const ms = msAllaFineDelRinvio(server, oraServer());
  if (ms !== null) timerRinvio = setTimeout(disegna, ms + 500);
}

// --- fotocamera e scatto

function accendiFotocamera() {
  if (flusso || accensione) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    queueMicrotask(() => vai('negata'));
    return;
  }
  accensione = navigator.mediaDevices
    .getUserMedia({ video: { facingMode: 'user', width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
    .then(async (nuovo) => {
      if (locale.fase !== 'anteprima') {
        nuovo.getTracks().forEach((traccia) => traccia.stop());
        return;
      }
      flusso = nuovo;
      const video = $('video');
      video.srcObject = flusso;
      await video.play();
    })
    .catch(() => {
      if (locale.fase === 'anteprima') vai('negata');
    })
    .finally(() => {
      accensione = null;
    });
}

function spegniFotocamera() {
  if (!flusso) return;
  flusso.getTracks().forEach((traccia) => traccia.stop());
  flusso = null;
  $('video').srcObject = null;
}

async function scattaFoto() {
  const video = $('video');
  if (!video.videoWidth) return; // la fotocamera non ha ancora un'immagine
  const tela = $('tela');
  tela.width = video.videoWidth;
  tela.height = video.videoHeight;
  tela.getContext('2d').drawImage(video, 0, 0);
  const blob = await new Promise((risolvi) => tela.toBlob(risolvi, 'image/jpeg', 0.9));
  if (!blob) {
    avvisa('Non sono riuscito a fare la foto: riprova.');
    return;
  }
  fotoPronta = blob;
  $('foto').src = URL.createObjectURL(blob);
  vai('scattata');
}

// «Foto ricevuta» compare solo se il servizio restituisce l'impronta dei byte
// che la pagina ha calcolato: un invio che non torna è un errore, mai un successo.
async function inviaFoto(evento) {
  vai(evento);
  avvisa('');
  const dati = await fotoPronta.arrayBuffer();
  const attesa = esadecimale(await crypto.subtle.digest('SHA-256', dati));
  try {
    const risposta = await conTentativi(() => api('PUT', `/api/giro/${server.giro.id}/foto`, dati, 'image/jpeg'));
    if (risposta.sha256 !== attesa) throw new Error('il servizio ha salvato una foto diversa da quella inviata');
    fotoPronta = null;
    vai('inviata');
    await aggiorna();
  } catch (errore) {
    if (errore.stato === 409 || errore.stato === 410) {
      fotoPronta = null;
      vai('respinta');
      avvisa(`Foto non inviata: ${errore.message}.`);
      await aggiorna();
      return;
    }
    vai('fallita');
    avvisa(`Invio non riuscito: ${errore.message}.`);
  }
}

function lasciaPerdere() {
  fotoPronta = null;
  vai('lascia_perdere');
  avvisa('Va bene. Se vuoi, puoi sempre mandare la foto su Telegram.');
}

async function salta() {
  try {
    await api('POST', `/api/giro/${server.giro.id}/rinvio`);
  } catch (errore) {
    avvisa(`Non sono riuscito a rimandare: ${errore.message}.`);
  }
  await aggiorna();
}

// --- pannello di master e admin

function formattaOra(iso) {
  return new Date(iso).toLocaleTimeString('it-CH', { hour: '2-digit', minute: '2-digit' });
}

function disegnaPannello() {
  $('pannello').hidden = !server.pannello;
  if (!server.pannello) return;
  $('stati').replaceChildren(
    ...server.pannello.map((riga) => {
      const voce = document.createElement('li');
      voce.textContent = `${riga.soprannome}: ${ETICHETTE_PANNELLO[riga.stato] ?? riga.stato}`;
      return voce;
    }),
  );
}

async function apriGiro() {
  $('apri-giro').disabled = true;
  try {
    $('esito-giro').textContent = esitoApertura(await api('POST', '/api/giro'), formattaOra);
  } catch (errore) {
    $('esito-giro').textContent = `Il giro non si è aperto: ${errore.message}.`;
  } finally {
    $('apri-giro').disabled = false;
  }
  await aggiorna();
}

// --- notifiche

async function registraServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  try {
    registrazione = await navigator.serviceWorker.register(`${base}sw.js`, { scope: base });
  } catch {
    registrazione = null;
  }
}

async function disegnaNotifiche() {
  $('suggerimento-ios').hidden = !('standalone' in navigator && !navigator.standalone);
  const possibile = registrazione && 'PushManager' in window && 'Notification' in window;
  if (!possibile) {
    $('notifiche').hidden = true;
    return;
  }
  const negate = Notification.permission === 'denied';
  $('notifiche-testo').textContent = negate
    ? 'Le notifiche sono bloccate: si riattivano dalle impostazioni del browser.'
    : "Vuoi ricevere l'invito anche a pagina chiusa?";
  $('attiva-notifiche').hidden = negate;
  const iscrizione = await registrazione.pushManager.getSubscription();
  $('notifiche').hidden = Notification.permission === 'granted' && iscrizione !== null;
}

// «Notifiche attivate» solo dopo che il servizio ha salvato l'iscrizione.
async function attivaNotifiche() {
  try {
    const permesso = await Notification.requestPermission();
    if (permesso !== 'granted') {
      avvisa('Notifiche non attivate: il permesso non è stato concesso.');
      return;
    }
    const iscrizione = await registrazione.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlInByte(server.vapid),
    });
    await api('POST', '/api/push', JSON.stringify(iscrizione.toJSON()), 'application/json');
    avvisa('Notifiche attivate.');
  } catch (errore) {
    avvisa(`Notifiche non attivate: ${errore.message}.`);
  } finally {
    disegna();
  }
}

// --- avvio

function collega() {
  for (const id of ['scatta', 'scatta-di-nuovo', 'scatta-ora', 'rifai-in-attesa']) {
    $(id).addEventListener('click', () => vai('scatta'));
  }
  $('salta').addEventListener('click', salta);
  $('scatta-foto').addEventListener('click', scattaFoto);
  $('annulla').addEventListener('click', () => vai('annulla'));
  $('invia').addEventListener('click', () => inviaFoto('invia'));
  $('rifai').addEventListener('click', () => vai('rifai'));
  $('riprova').addEventListener('click', () => inviaFoto('riprova'));
  $('lascia-perdere').addEventListener('click', lasciaPerdere);
  $('riprova-fotocamera').addEventListener('click', () => vai('riprova'));
  $('annulla-fotocamera').addEventListener('click', () => vai('annulla'));
  $('attiva-notifiche').addEventListener('click', attivaNotifiche);
  $('apri-giro').addEventListener('click', apriGiro);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') aggiorna();
  });
}

collega();
await registraServiceWorker();
await aggiorna();
setInterval(aggiorna, 20000);
```

`web/sw.js`:

```js
// Il service worker della pagina personale. Il suo ambito è /p/<gettone>/:
// al tocco sulla notifica apre proprio quella pagina, senza che il servizio
// debba conoscere il gettone. Il carico utile è {"titolo", "testo"} (push.py).

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

self.addEventListener('push', (evento) => {
  let dati = { titolo: 'Radiant Selfie Machine', testo: '' };
  try {
    dati = evento.data.json();
  } catch {
    // un push senza JSON mostra comunque il titolo
  }
  evento.waitUntil(
    self.registration.showNotification(dati.titolo, {
      body: dati.testo,
      icon: '/static/icona-192.png',
      tag: 'radiant-selfie-machine',
      renotify: true,
    }),
  );
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil(
    (async () => {
      const finestre = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const finestra of finestre) {
        if (finestra.url.startsWith(self.registration.scope)) return finestra.focus();
      }
      return self.clients.openWindow(self.registration.scope);
    })(),
  );
});
```

`strumenti/icone.py`:

```python
"""Disegna le due icone della pagina. Si lancia una volta, e le icone si
committano:  uv run python strumenti/icone.py"""

from pathlib import Path

from PIL import Image, ImageDraw

CARTELLA = Path(__file__).resolve().parents[1] / "web" / "static"
FONDO = (43, 26, 74)
ORO = (242, 200, 90)
VIOLA = (160, 120, 255)


def icona(lato: int) -> Image.Image:
    immagine = Image.new("RGB", (lato, lato), FONDO)
    disegno = ImageDraw.Draw(immagine)
    margine = lato // 8
    disegno.rounded_rectangle(
        [margine, lato * 3 // 10, lato - margine, lato * 3 // 4], radius=lato // 12, fill=ORO
    )
    disegno.rectangle([lato * 3 // 8, lato // 5, lato * 5 // 8, lato * 3 // 10], fill=ORO)
    cx, cy = lato // 2, lato * 55 // 100
    for raggio, colore in ((lato * 16 // 100, FONDO), (lato // 10, VIOLA)):
        disegno.ellipse([cx - raggio, cy - raggio, cx + raggio, cy + raggio], fill=colore)
    return immagine


if __name__ == "__main__":
    for lato in (192, 512):
        icona(lato).save(CARTELLA / f"icona-{lato}.png")
```

Poi:

```bash
mkdir -p strumenti
uv run python strumenti/icone.py
git rm -q web/static/.gitkeep
```

- [ ] **Step 4: installa il pilota di Chrome per Playwright, se serve, e lancia le prove**

Playwright usa il Chrome già installato (`channel="chrome"`): non scarica browser.

Run: `uv run pytest -m e2e -q`
Expected: 3 PASS. Se fallisce con «Executable doesn't exist», il Chrome di sistema non è stato trovato: verifica `/Applications/Google Chrome.app`.

Run anche: `uv run pytest -q && node --test "web/test/*.test.js" && uv run ruff check src tests strumenti`
Expected: tutto PASS.

- [ ] **Step 5: prova a mano, una volta, nel tuo browser**

Avvia il servizio in locale come nello step 6 del Task 12, aggiungi due persone con `RSM_DB=dati/prova/rsm.sqlite RSM_URL_BASE=http://127.0.0.1:8471 uv run rsm persona aggiungi gio --ruolo master` (e `emi --ruolo giocatore`), apri i due link in due finestre di Chrome, apri il giro da quella di gio, scatta e invia da quella di emi. Controlla a occhio: l'anteprima è a specchio, la foto rivista pure, il pannello di gio passa a «in attesa di validazione». Poi ferma il servizio e `rm -rf dati/prova`.

- [ ] **Step 6: commit**

```bash
git add web/index.html web/static/stile.css web/static/app.js web/sw.js web/static/icona-192.png web/static/icona-512.png strumenti/icone.py tests/e2e
git commit -m "the page, service worker, icons, and Chrome end-to-end tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 16: il container, la messa in produzione, il README

Il servizio gira in Docker sulla macchina di Nextcloud (AIO, x86_64), dietro il Nginx di Alberto, su `selfie.esempio.duckdns.org`. Sul Mac Docker non c'è: l'immagine si costruisce e si prova sul server, seguendo `docs/messa-in-produzione.md`. Qui si scrivono i file e si verifica ciò che si può verificare in locale.

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `compose.yaml`, `config.esempio/rsm.env`, `docs/messa-in-produzione.md`, `README.md`

**Interfaces:**
- Consumes: `rsm.principale:costruisci` (Task 12); il comando `rsm` (Task 13); le variabili d'ambiente di `config.da_ambiente` (Task 6) più `RSM_WEB` e `RSM_URL_BASE`; `/salute` (Task 12); i test `-m reale` (Task 17).
- Produces: un'immagine con due bersagli, `servizio` (il servizio) e `prova` (con i test e le dipendenze di sviluppo, per il piano reale); un `compose.yaml` con il servizio `rsm` in ascolto solo su `127.0.0.1:8470` e il servizio `prova` sotto il profilo `prova`.

- [ ] **Step 1: scrivi i file del container**

`Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY web ./web
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" RSM_WEB=/app/web

FROM base AS servizio
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salute', timeout=3)"
# --no-access-log: il percorso della pagina contiene il gettone.
CMD ["uvicorn", "--factory", "rsm.principale:costruisci", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM base AS prova
COPY tests ./tests
RUN uv sync --frozen
CMD ["pytest", "-m", "reale", "-rs", "tests/reale"]
```

`.dockerignore`:

```
.git
.venv
__pycache__
.pytest_cache
.ruff_cache
dati
config
docs
```

`compose.yaml`:

```yaml
services:
  rsm:
    build:
      context: .
      target: servizio
    restart: unless-stopped
    env_file: ./config/rsm.env
    volumes:
      - ./dati:/data
      - ./config:/config:ro
    ports:
      # Solo il Nginx della macchina arriva qui: nessuna porta aperta verso fuori.
      - "127.0.0.1:8470:8000"

  prova:
    profiles: ["prova"]
    build:
      context: .
      target: prova
    env_file: ./config/rsm.env
    volumes:
      - ./dati:/data
      - ./config:/config:ro
```

`config.esempio/rsm.env`:

```
# Copia in config/rsm.env sul server, poi: chmod 600 config/rsm.env
# Contiene il token del bot: non va mai nel repository.

RSM_DB=/data/rsm.sqlite
RSM_FOTO=/data/foto
RSM_URL_BASE=https://selfie.esempio.duckdns.org

# Il bot del servizio (nuovo, separato da quello di ctc), da @BotFather.
RSM_BOT_TOKEN=

# Il gruppo di prova: Alberto e il bot, nessun altro.
RSM_GRUPPO_PROVA=

# La sicura. Finché è vuoto, l'annuncio va nel gruppo di prova.
# Si arma scrivendo qui l'identificativo del gruppo del party (è nel roster di
# ctc, chiave «party»), dopo la prova generale, e poi: docker compose up -d
RSM_GRUPPO=

# L'identificativo Telegram di Alberto: l'unico che può validare.
RSM_ADMIN_TELEGRAM_ID=123456789

# La chiave VAPID, generata con «rsm vapid genera» (v. docs/messa-in-produzione.md).
RSM_VAPID_PEM=/config/vapid.pem
# Un indirizzo tuo: i servizi push lo usano per contattarti se qualcosa non va.
RSM_VAPID_CONTATTO=mailto:

RSM_RINVIO_MINUTI=10

# Per il piano reale (docker compose --profile prova run --rm prova):
# RSM_REALE_GETTONE=      il gettone della persona «prova» (ruolo giocatore)
# RSM_REALE_PUSH_A=       chi riceve il push di prova, dopo aver attivato le notifiche
```

- [ ] **Step 2: scrivi la guida di messa in produzione**

`docs/messa-in-produzione.md`:

````markdown
# Messa in produzione

Sulla macchina di Nextcloud (AIO, x86_64), dietro il Nginx di Alberto. Una
volta sola, in quest'ordine. I comandi che leggono il token del bot lo prendono
dal file, senza mai scriverlo nella riga di comando.

## 1. Il bot e il gruppo di prova

1. Su Telegram, da **@BotFather**: `/newbot`, nome «Radiant Selfie Machine».
   Il token va in `config/rsm.env` (punto 3), da nessun'altra parte.
2. Crea un gruppo «RSM prova» con te e il bot, nessun altro.
3. Scrivi `/start` al bot **in privato**: senza, il bot non può scriverti, e le
   foto da validare non ti arriverebbero.

## 2. Il codice

Porta il repository sul server (un `git clone` dal remoto che preferisci, o una
copia della cartella senza `.venv`, `dati` e `config`), entra nella cartella e:

```bash
mkdir -p config dati
```

## 3. La configurazione

```bash
cp config.esempio/rsm.env config/rsm.env
chmod 600 config/rsm.env
```

Compila `config/rsm.env`: token del bot e contatto VAPID. **Lascia
`RSM_GRUPPO` vuoto**: è la sicura.

Poi l'identificativo del gruppo di prova: scrivi un messaggio qualsiasi nel
gruppo e, sul server, prima di avviare il servizio (acceso, si prenderebbe lui
gli aggiornamenti):

```bash
TOKEN=$(grep -oP '^RSM_BOT_TOKEN=\K.*' config/rsm.env)
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | grep -o '"chat":{"id":-[0-9]*' | sort -u
unset TOKEN
```

Il numero negativo che compare va in `RSM_GRUPPO_PROVA`.

## 4. La chiave VAPID

`config` è montata in sola lettura nel servizio: per generare la chiave si
monta una seconda volta, scrivibile, solo per questo comando.

```bash
docker compose build rsm
docker compose run --rm --no-deps -v "$PWD/config:/nuova" rsm rsm vapid genera /nuova/vapid.pem
```

Il file nasce con i permessi 600. Non va rigenerato: una chiave nuova rende
inutili tutte le iscrizioni push già fatte.

## 5. Nginx e il certificato

Un blocco nuovo, accanto a quello di Nextcloud. `client_max_body_size` è
obbligatorio: per default Nginx rifiuta i corpi oltre 1 MB, e la foto vera
fallirebbe con un 413 di Nginx, non nostro.

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name selfie.esempio.duckdns.org;

    ssl_certificate     /etc/letsencrypt/live/selfie.esempio.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/selfie.esempio.duckdns.org/privkey.pem;

    client_max_body_size 9m;

    location / {
        proxy_pass http://127.0.0.1:8470;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Il sottodominio risolve già all'indirizzo della macchina (DuckDNS risolve ogni
sottodominio). Il certificato: con certbot, `certbot --nginx -d
selfie.esempio.duckdns.org`, oppure con il metodo che già usi per
Nextcloud. Poi `nginx -t && systemctl reload nginx`.

## 6. Avvio

```bash
docker compose up -d --build
curl -fsS https://selfie.esempio.duckdns.org/salute
```

Atteso: `{"ok":true}`.

## 7. Le persone

```bash
docker compose exec rsm rsm persona aggiungi gio --ruolo master
docker compose exec rsm rsm persona aggiungi emi --ruolo giocatore
docker compose exec rsm rsm persona aggiungi sem --ruolo giocatore
docker compose exec rsm rsm persona aggiungi sese --ruolo giocatore
docker compose exec rsm rsm persona aggiungi pippo --ruolo giocatore
docker compose exec rsm rsm persona aggiungi abe --ruolo admin
docker compose exec rsm rsm persona aggiungi ctc --ruolo ctc
```

Ogni comando stampa il link **una volta sola**: consegnalo in privato. Il
gettone di `ctc` va nel portachiavi del Mac (lo farà il piano di `ctc`). Un
link perso o finito nelle mani sbagliate: `rsm persona revoca <soprannome>`.

## 8. Il piano reale e la prova generale

```bash
docker compose exec rsm rsm persona aggiungi prova --ruolo giocatore
```

Metti il gettone stampato in `RSM_REALE_GETTONE` dentro `config/rsm.env`; attiva
le notifiche dalla tua pagina e metti `RSM_REALE_PUSH_A=abe`. Poi:

```bash
docker compose --profile prova run --rm prova
```

Il piano reale è verde solo se **non salta niente**: un test saltato non è un
test superato. Alla fine `docker compose exec rsm rsm persona rimuovi prova`,
altrimenti `ctc doctor` la segnalerà come persona che il roster non conosce.

La prova generale: tu e un giocatore, con la sicura inserita. Apri il giro, lui
scatta, tu validi dal bot, e chiedi un'altra foto almeno una volta con un
motivo.

## 9. Armare la sicura

Solo dopo la prova generale: scrivi l'identificativo del party in `RSM_GRUPPO`
dentro `config/rsm.env`, poi `docker compose up -d`. La risposta a «Apri il
giro» passerà da «gruppo di prova» a «gruppo del party».

## Aggiornare

```bash
git pull && docker compose up -d --build
```
````

- [ ] **Step 3: scrivi il README**

`README.md`:

````markdown
# Radiant Selfie Machine

La pagina web con cui chi siede al tavolo dei *Danni Radiosi* scatta il selfie
per la miniatura quando il master apre il giro, e il servizio che lo raccoglie
per `close-the-circle`. Alberto valida ogni foto dal bot Telegram.

Il design sta in `docs/superpowers/specs/`, il piano in `docs/superpowers/plans/`.
Leggi la specifica prima di cambiare il comportamento: molte scelte hanno un
motivo che il codice da solo non spiega.

## Sviluppo

Richiede [uv](https://docs.astral.sh/uv/), Node (per i test della pagina) e
Chrome (per le prove da capo a fondo).

```bash
uv sync
uv run pytest -q                      # la suite veloce
node --test "web/test/*.test.js"      # la macchina a stati della pagina
uv run pytest -m e2e -q               # tre prove in Chrome con la webcam finta
uv run ruff check src tests strumenti
```

Il piano reale (`-m reale`) si lancia sul server, contro i sistemi veri: v.
`docs/messa-in-produzione.md`. Le convinzioni che i finti mettono per iscritto,
e dove vengono verificate, stanno in `docs/differenze-fra-test-e-realta.md`.

## In produzione

Sulla macchina di Nextcloud, in Docker, dietro Nginx:
`docs/messa-in-produzione.md`. Finché `RSM_GRUPPO` è vuoto, il bot annuncia il
giro nel gruppo di prova.
````

- [ ] **Step 4: verifica quello che si può verificare sul Mac**

Run: `uv lock --check && uv run pytest -q && node --test "web/test/*.test.js"`
Expected: il lock è coerente con `pyproject.toml`; tutto PASS. L'immagine Docker si costruisce e si prova sul server (guida, punti 4-6): è lì che Alberto conferma che `docker compose up -d --build` arriva a `{"ok":true}`.

- [ ] **Step 5: commit**

```bash
git add Dockerfile .dockerignore compose.yaml config.esempio/rsm.env docs/messa-in-produzione.md README.md
git commit -m "container, deployment guide, README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: il piano reale

Un test di contratto per ogni sistema esterno, contro il vero: il bot Telegram, il servizio push, il servizio pubblicato dietro Nginx. Si lanciano dentro il container `prova` sul server, con la configurazione vera. Una variabile mancante fa saltare il test **dicendo quale contratto resta non verificato**; il piano reale è verde solo quando non salta niente.

**Files:**
- Create: `tests/reale/__init__.py`, `tests/reale/ambiente.py`, `tests/reale/test_telegram_vero.py`, `tests/reale/test_push_vero.py`, `tests/reale/test_servizio_pubblicato.py`
- Modify: `docs/differenze-fra-test-e-realta.md` (colonna «Dove si verifica», se un test cambia nome o scopo mentre lo scrivi)

**Interfaces:**
- Consumes: `BotTelegram` (Task 4); `Notificatore` (Task 5); `Store` (Task 3); `pulsanti.tastiera`, `MOTIVI_PREDEFINITI` (Task 6); `CSP` (Task 12); `gettoni.genera` (Task 2); `tests.immagini.jpeg` (Task 2). Variabili: `RSM_BOT_TOKEN`, `RSM_GRUPPO_PROVA`, `RSM_ADMIN_TELEGRAM_ID`, `RSM_DB`, `RSM_VAPID_PEM`, `RSM_VAPID_CONTATTO`, `RSM_URL_BASE` (già in `config/rsm.env`), `RSM_REALE_GETTONE`, `RSM_REALE_PUSH_A`.
- Produces: `tests.reale.ambiente.richiesta(nome: str) -> str`.

- [ ] **Step 1: scrivi l'aiuto e i tre contratti**

`tests/reale/__init__.py`: vuoto.

`tests/reale/ambiente.py`:

```python
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
```

`tests/reale/test_telegram_vero.py`:

```python
"""Il bot vero. Si può lanciare con il servizio acceso: questi test scrivono e
basta, e scrivere non ruba gli aggiornamenti al ciclo del servizio."""

import pytest

from rsm import pulsanti
from rsm.config import MOTIVI_PREDEFINITI
from rsm.telegram import BotTelegram
from tests.immagini import jpeg
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def bot():
    return BotTelegram(richiesta("RSM_BOT_TOKEN"))


def test_nessun_webhook_quindi_il_long_polling_funziona():
    assert bot().webhook_attivo() is False


def test_scrive_nel_gruppo_di_prova():
    gruppo = int(richiesta("RSM_GRUPPO_PROVA"))
    messaggio = bot().scrivi(gruppo, "🧪 Prova del piano reale di Radiant Selfie Machine: ignorate.")
    assert isinstance(messaggio, int)


def test_manda_ad_alberto_una_foto_con_i_pulsanti_e_la_modifica():
    """Contratto: Alberto ha scritto /start al bot, sendPhoto in multipart con la
    tastiera funziona, e editMessageCaption toglie i pulsanti."""
    alberto = int(richiesta("RSM_ADMIN_TELEGRAM_ID"))
    b = bot()
    messaggio = b.manda_foto(
        alberto,
        jpeg(640, 480),
        "🧪 Prova del piano reale: ignora i pulsanti",
        pulsanti.tastiera(0, "prova", 1, MOTIVI_PREDEFINITI),
    )
    b.modifica_didascalia(alberto, messaggio, "🧪 Prova del piano reale: conclusa")
```

`tests/reale/test_push_vero.py`:

```python
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
```

`tests/reale/test_servizio_pubblicato.py`:

```python
"""Il servizio come lo vede un browser da fuori: HTTPS con un certificato
valido (httpx lo verifica), Nginx davanti, le intestazioni giuste."""

import httpx
import pytest

from rsm import gettoni
from rsm.app import CSP
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def url():
    return richiesta("RSM_URL_BASE").rstrip("/")


def test_risponde_in_https_con_un_certificato_valido():
    risposta = httpx.get(f"{url()}/salute", timeout=10)
    assert risposta.status_code == 200
    assert risposta.json() == {"ok": True}


def test_un_gettone_inventato_riceve_404():
    assert httpx.get(f"{url()}/p/{gettoni.genera()}/", timeout=10).status_code == 404


def test_la_pagina_ha_la_csp_e_il_manifest_giusto():
    gettone = richiesta("RSM_REALE_GETTONE")
    pagina = httpx.get(f"{url()}/p/{gettone}/", timeout=10)
    assert pagina.status_code == 200
    assert pagina.headers["content-security-policy"] == CSP
    manifest = httpx.get(f"{url()}/p/{gettone}/manifest.webmanifest", timeout=10).json()
    assert manifest["start_url"] == f"/p/{gettone}/"


def test_nginx_lascia_passare_una_foto_da_7_mb_e_mezzo():
    """Senza client_max_body_size, Nginx risponde 413 con una sua pagina HTML
    prima che la foto arrivi al servizio. Qui la risposta attesa è il 404 JSON
    del servizio: il giro 999999 non esiste, ma il corpo è arrivato fin lì."""
    gettone = richiesta("RSM_REALE_GETTONE")
    risposta = httpx.put(
        f"{url()}/api/giro/999999/foto",
        content=b"\xff" * (7 * 1024 * 1024 + 512 * 1024),
        headers={"Authorization": f"Bearer {gettone}", "Content-Type": "image/jpeg"},
        timeout=60,
    )
    assert risposta.status_code == 404
    assert "errore" in risposta.json()
```

- [ ] **Step 2: verifica che in locale, senza variabili, tutto salti dicendo perché**

Run: `uv run pytest -m reale -rs -q`
Expected: tutti i test SKIPPED, e l'elenco dei salti nomina la variabile mancante e «questo contratto NON è stato verificato». Nessun errore d'import.

Run anche: `uv run pytest -q && uv run ruff check src tests strumenti`
Expected: la suite veloce non cambia e resta verde (i test reali sono esclusi di default).

- [ ] **Step 3: aggiorna le differenze fra test e realtà**

Rileggi `docs/differenze-fra-test-e-realta.md` e controlla che ogni riga della colonna «Dove si verifica» nomini un test che esiste davvero con quel nome. Correggi le righe che non tornano.

- [ ] **Step 4: commit**

```bash
git add tests/reale docs/differenze-fra-test-e-realta.md
git commit -m "real-world contract tests: bot, push service, published service

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: fine del ramo**

Tutti i task sono chiusi. Lancia per l'ultima volta:

```bash
uv run pytest -q && node --test "web/test/*.test.js" && uv run pytest -m e2e -q && uv run ruff check src tests strumenti
```

Expected: tutto verde. Il ramo `servizio-e-pagina` **non** si fonde in `main` senza l'assenso esplicito di Alberto. La messa in produzione (Task 16, guida) e il piano reale sul server li fa Alberto, o si fanno insieme a lui.
