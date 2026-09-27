# Radiant Selfie Machine — design

Data: 2026-09-27 · Stato: approvato a sezioni in brainstorming, da rileggere

Una pagina web installabile con cui chi siede al tavolo dei *Danni Radiosi*
scatta il selfie per la miniatura dalla propria webcam, quando il master apre il
«giro».
Le foto arrivano a `close-the-circle` (`ctc`) già con un nome, invece di dover
essere riconosciute fra i messaggi di Telegram.

Collegato a `close-the-circle`
(`~/git/python/close-the-circle`), di cui questo progetto cambia la
fase 1, la fase 2 e i solleciti. Le modifiche a `ctc` stanno nella §10 e
avranno un piano proprio, nel repository di `ctc`.

## 1. Perché

Oggi i cinque giocatori mandano il selfie su due gruppi Telegram. `ctc` lo
legge con Telethon, sceglie un candidato fra le foto della finestra, chiede ad
Alberto di confermarlo e sollecita chi manca. La parte fragile è tutta lì:
capire di chi è una foto, scegliere fra più foto, confermare — con la
conferma bloccante perché una foto accettata per errore è un sollecito che non
parte.

Una foto scattata dalla pagina personale di un giocatore arriva **con
l'identità certa** e **scelta da chi l'ha scattata**. Resta una sola domanda da
fare ad Alberto: «la foto va bene?». Telegram diventa il ripiego.

Il criterio di successo di `ctc` non cambia: Alberto va a letto subito.

## 2. Decisioni

| Decisione | Motivo |
|---|---|
| **Pagina web installabile**, non un eseguibile | Una sola base di codice per Windows, macOS, Linux, Android e iOS. Niente firme, niente store, aggiornamenti immediati. Un eseguibile non firmato va sbloccato a mano su macOS e Windows, e per l'iPhone serviva comunque una pagina web (niente account Apple Developer). |
| Scartati Flutter e Compose Multiplatform | Su desktop la webcam di Flutter poggia su plugin non ufficiali e giovani (`camera_windows`, `camera_desktop`); Compose su una libreria di un solo manutentore, con JavaCV. Verificato il 27/09/2026. |
| **Il master (gio) o Alberto aprono il giro**; ogni giocatore è libero di scattare o no | Richiesta di Alberto. |
| **«Salta» rimanda l'invito di X minuti** (predefinito 10), senza limite di volte | Richiesta di Alberto: non è una rinuncia. Chi non scatta mai viene sollecitato come oggi. |
| **Telegram resta come ripiego** | Chi non usa la pagina manda la foto nel gruppo; `ctc` legge entrambe le fonti. |
| **Invito: messaggio nel gruppo e Web Push** | Il messaggio nel gruppo arriva a tutti; il push porta alla pagina anche chiusa, rende vero il rinvio di «Salta» sul telefono e raggiunge un solo giocatore per la richiesta di un'altra foto. La consegna push non è garantita, per questo il gruppo resta. |
| **Alberto valida ogni foto** («Va bene» / «Chiedi un'altra foto») | Richiesta di Alberto. Solo una foto validata è definitiva. |
| **Chi rifiuta una foto può dirne il motivo**, e il motivo accompagna la richiesta di un'altra foto e il sollecito | Richiesta di Alberto: chi deve rifare la foto sa cosa cambiare. Per lo stesso principio il sollecito dice anche quando il servizio non rispondeva. |
| **Anche Alberto scatta dalla pagina**, durante il giro | Richiesta di Alberto: con la pagina ha anteprima e conferma, che la webcam di `ctc tonight` non gli dà. La webcam resta il ripiego. |
| **Servizio sulla macchina di Nextcloud** (AIO, x86_64, dietro il Nginx di Alberto) | Già raggiungibile in HTTPS; `selfie.esempio.duckdns.org` risolve già al suo IP. |
| **Python + FastAPI + SQLite**, in Docker | Stessi strumenti di `ctc` (uv, pytest, ruff). |
| **Un bot Telegram nuovo**, separato da quello di `ctc` | Il bot del servizio deve leggere i tocchi di Alberto sui pulsanti; due programmi non possono leggere lo stesso bot. E il token di `ctc` resta nel portachiavi del Mac. |

## 3. Il giro dei selfie

1. **Apertura.** Il master o Alberto preme «Apri il giro» sulla propria pagina.
   Il servizio registra il giro, il bot scrive nel gruppo del party
   («📸 È il momento del selfie per la miniatura!», senza link: ognuno ha la sua
   pagina) e parte una notifica push a chiunque si sia iscritto: giocatori,
   master e Alberto.
2. **Invito.** La pagina aperta controlla lo stato ogni 20 secondi e mostra
   l'invito da sola; chiusa, lo mostra quando si tocca la notifica.
3. **Scatto.** Anteprima della webcam con «Scatta» e «Salta». Dopo lo scatto la
   foto si rivede: «Invia» o «Rifai».
4. **Salta.** Il servizio annota un rinvio di X minuti; allo scadere manda di
   nuovo il push, e la pagina aperta ripropone l'invito. Senza limite.
5. **Validazione.** Ogni foto ricevuta arriva ad Alberto in privato dal bot. I
   pulsanti sono «Va bene», un pulsante per ciascun motivo predefinito
   («Sfocata», «Troppo buia», «Viso non inquadrato», «Tagliata»), «Altro
   motivo…» e
   «Un'altra, senza motivo»: un tocco solo, nel caso comune, decide e motiva
   insieme. «Altro motivo…» chiede il testo in risposta; la foto resta in attesa
   finché il testo non arriva, e il messaggio del bot lo dice. Finché la foto è
   in attesa, il giocatore può rifarla: la nuova sostituisce la vecchia e ad
   Alberto arriva un nuovo messaggio. Se Alberto chiede un'altra foto, la pagina
   del giocatore mostra la richiesta con il motivo («Alberto chiede un'altra
   foto: troppo buia») e riattiva la fotocamera, e gli arriva un push con lo
   stesso testo. Un motivo predefinito ha un'etichetta corta per il pulsante e
   un testo per il giocatore, che può essere più lungo: «Tagliata» diventa
   «tagliata (controlla che tutta la testa sia ben visibile nella foto)». Una
   foto accettata è definitiva: la pagina mostra «La tua foto è stata accettata»,
   non offre più «Rifai», e al giocatore arriva un push con lo stesso testo.
   Se il sollecito gli aveva promesso una conferma, arriva anche un messaggio
   privato (§10.10).
6. **Fuori da un giro** la pagina mostra «Nessun giro aperto» e non accende la
   fotocamera.
7. **Raccolta.** `ctc` lega il giro alla sessione e scarica le foto (§10).
8. **Chiusura.** Un giro si chiude da solo 48 ore dopo l'apertura. «Apri il
   giro» con un giro aperto da meno di 12 ore non fa niente («Giro già aperto
   alle 22:10»); con uno più vecchio, lo chiude e ne apre uno nuovo. Due serate
   non stanno mai a meno di 12 ore l'una dall'altra.

**Il selfie di Alberto** (`abe`) si scatta dalla stessa pagina, durante il
giro, con la stessa anteprima e lo stesso «Invia» / «Rifai». Non passa dalla
validazione: il suo «Invia» è già la conferma di chi valida, e la foto è
accettata all'arrivo. Se non c'è, `ctc tonight` la scatta con la webcam come
oggi (§10).

## 4. I pezzi

```
Pagina (browser, installata) ──HTTPS──▶ Servizio (Docker, dietro Nginx) ──▶ Bot ▶ gruppo del party
        ▲                                 │  SQLite + cartella foto      ──▶ Bot ▶ Alberto (validazione)
        └──── Web Push ◀──────────────────┤
ctc sul Mac ◀──HTTPS, gettone admin───────┘
```

### Il servizio (`rsm`)

Moduli piccoli, ognuno con un compito, come in `ctc`:

| Modulo | Compito |
|---|---|
| `regole.py` | Le regole pure: apertura e riapertura del giro, scadenza, stati di una foto e transizioni ammesse, rinvii. Orologio iniettato. Nessun I/O. |
| `store.py` | SQLite: persone, giri, foto, rinvii, iscrizioni push. |
| `gettoni.py` | Generazione dei gettoni e hash. |
| `foto.py` | Validazione del JPEG, SHA-256, salvataggio nel volume. |
| `telegram.py` | Client del bot: scrivere nel gruppo, mandare ad Alberto la foto con i pulsanti, leggere i tocchi e le risposte di testo (long polling). **Nessuna politica.** |
| `push.py` | Invio Web Push con `pywebpush`; toglie le iscrizioni che il servizio push dichiara scadute (404/410). |
| `pianificatore.py` | Un ciclo ogni 30 secondi: rinvii scaduti di chi non ha ancora una foto in attesa o accettata → push; giri scaduti → chiusi; foto di giri chiusi da più di 30 giorni → cancellate. |
| `app.py` | Le rotte FastAPI, sottili: autenticano, chiamano `regole` e `store`, rispondono. |
| `cli.py` | `rsm persona aggiungi <soprannome> --ruolo …`, `revoca`, `elenco`. |

### La pagina (`web/`)

HTML, CSS e JavaScript senza framework e senza build.

- `stati.js` — la macchina a stati, senza dipendenze dal browser: nessun giro,
  invito, rinviato, anteprima, revisione, invio, errore di invio, in attesa di
  validazione, accettata, nuova foto richiesta (con il motivo, se c'è),
  fotocamera negata.
- `app.js` — `getUserMedia`, scatto su canvas, JPEG, invio, polling, pulsante
  «Attiva le notifiche» (il permesso va chiesto da un gesto dell'utente:
  Safari lo impone).
- `sw.js` — il service worker: riceve il push, mostra la notifica, al tocco
  apre o porta in primo piano la pagina personale.
- Il manifest è **per persona** (`/p/<gettone>/manifest.webmanifest`, con
  `start_url` = `/p/<gettone>`), perché l'app installata deve ripartire dal suo
  link (§6).
- Tutti scattano dalla stessa schermata. Master e admin vedono in più il
  pannello del giro: «Apri il giro» e lo stato di ogni persona (nessuna foto,
  rinviato, in attesa, accettata, da rifare) — i nomi e gli stati, non le foto.

## 5. API del servizio

Autenticazione: `Authorization: Bearer <gettone>` su ogni rotta `/api/`. Un
gettone assente o non valido riceve **404**, come una pagina che non esiste.
Le date viaggiano in ISO 8601 con fuso (UTC nel database).

| Rotta | Ruoli | Effetto |
|---|---|---|
| `GET /p/{gettone}` | tutti | La pagina. |
| `GET /p/{gettone}/manifest.webmanifest` | tutti | Il manifest della persona. |
| `GET /api/stato` | tutti | Persona, ruolo, giro aperto (id, apertura, scadenza) o nessuno, stato della propria foto con SHA-256 e l'eventuale motivo del rifiuto, fine del rinvio, chiave VAPID pubblica. Per master e admin anche lo stato di ogni persona. |
| `POST /api/giro` | master, admin | Apre il giro o restituisce quello aperto (§3.8). La risposta dice se l'annuncio nel gruppo è partito. |
| `PUT /api/giro/{id}/foto` | tutti | Corpo `image/jpeg`. Crea la propria foto, o sostituisce quella in attesa o da rifare; il nuovo stato è «in attesa», oppure «accettata» per la foto di `abe` (§3). Risponde con SHA-256 e byte salvati. **409** se la foto è già accettata, **410** se il giro è chiuso, **413** oltre gli 8 MB, **415** se non è un JPEG decodificabile. |
| `POST /api/giro/{id}/rinvio` | tutti | Rinvio di X minuti. |
| `POST /api/push` · `DELETE /api/push` | tutti | Iscrizione e cancellazione push del dispositivo. |
| `GET /api/giri?dal=…` | admin | I giri aperti da quel momento, con la sessione a cui sono legati. |
| `POST /api/giro/{id}/lega` | admin | Corpo `{"sessione": "AAAA-MM-GG"}`. Idempotente per la stessa sessione; **409** se il giro è già legato a un'altra. |
| `GET /api/giro/{id}/foto` | admin | Per ogni persona: stato, SHA-256 e l'eventuale motivo del rifiuto. |
| `GET /api/giro/{id}/foto/{soprannome}` | admin | I byte della foto. **Nessun effetto collaterale**: se `ctc` fallisce dopo averla scaricata, il servizio non deve credere la foto archiviata. Quello che è archiviato lo dice `Miniatura/`. |
| `POST /api/giro/{id}/foto/{soprannome}/esito` | admin | Corpo `{"esito": "accettata" \| "da_rifare", "motivo": "…"}`, motivo facoltativo e solo con `da_rifare`, al massimo 200 caratteri: la validazione fatta da `ctc` a video. |

I tocchi sui pulsanti del bot, e il testo di «Altro motivo…», fanno la stessa
transizione di `…/esito`, e sono accettati **solo** dall'identificativo Telegram
di Alberto (configurazione). Il motivo viaggia sempre come testo semplice, mai
interpretato come formattazione.
Un tocco su una foto nel frattempo sostituita risponde «foto sostituita» e non
cambia niente.

## 6. Identità e confini

- **Gettoni.** 32 byte casuali, codificati per URL. Nel database solo lo
  SHA-256. `rsm persona aggiungi` stampa il link una volta sola; `revoca` lo
  annulla e ne genera un altro. Chi ha il link può scattare al posto della
  persona: è un segreto, come un link di condivisione di Nextcloud.
- **Il gettone sta nel percorso** (`/p/<gettone>`), non in un cookie: su iPhone
  l'app aggiunta alla schermata Home non condivide la memoria di Safari e deve
  poter ripartire dal solo link. Il prezzo è il gettone nei log di Nginx:
  accettato, per sei persone.
- **Ruoli.** Giocatore: scatta. Master (gio): scatta e apre il giro. Admin:
  scatta, apre il giro, vede gli stati, scarica e valida — è il link personale
  di Alberto, più `ctc`, che usa un gettone admin suo e non scatta mai.
- **Persone del servizio:** gio (master), emi, sem, sese, pippo (giocatori),
  abe (admin). I soprannomi sono quelli del roster di `ctc` e passano la stessa
  validazione (`^[a-z0-9_-]{1,32}$`). La lista è una copia tenuta a mano;
  `ctc doctor` segnala le differenze (§10).
- **Foto.** Solo JPEG, al massimo 8 MB, che Pillow riesce a decodificare. Una
  foto uscita dal canvas non ha EXIF, quindi nemmeno la posizione.
- **Segreti.** Token del bot e chiavi VAPID in un file di configurazione sul
  server con permessi `600`, mai nel repository. Il gettone admin di `ctc` nel
  portachiavi del Mac, come gli altri segreti di `ctc`.
- **La sicura.** Finché `RSM_GRUPPO` non contiene l'identificativo del party, il
  bot scrive in un gruppo di prova. Si arma dopo una prova generale fra Alberto
  e un giocatore, dal file di configurazione — mai in un modo che non lasci
  traccia in un file che si rilegge.

## 7. Casi limite ed errori

Le tre corse vere di `ctc` hanno trovato difetti della stessa famiglia: non
errori, ma **messaggi falsi**. Qui ogni messaggio afferma solo ciò che è stato
verificato.

1. **«Foto ricevuta»** solo quando lo SHA-256 restituito dal servizio coincide
   con quello calcolato dalla pagina. Un invio fallito si ritenta da solo tre
   volte; poi «Invio non riuscito», con «Riprova» (ripetibile senza limite) e
   «Lascia perdere», che scarta la foto e ricorda il ripiego Telegram. Una foto
   non si perde mai in silenzio.
2. **Foto accettata = definitiva** (§3.5). Il servizio rifiuta con 409 un invio
   su una foto accettata, e la pagina lo spiega.
3. **Il bot non riesce a scrivere nel gruppo.** Il giro resta aperto; la pagina
   del master mostra «Giro aperto, ma il messaggio nel gruppo non è partito».
4. **Il bot non riesce a scrivere ad Alberto.** La foto resta in attesa e il
   pannello admin la mostra come tale; `ctc` la proporrà a video (§10).
5. **«Altro motivo…» senza testo.** La foto resta in attesa, e il messaggio del
   bot dice che aspetta il motivo: nessuna richiesta parte senza che Alberto
   l'abbia completata. Se il testo non arriva mai, `ctc` propone la foto a
   video come ogni foto in attesa.
6. **Push.** Un'iscrizione che il servizio push dichiara scaduta (404/410) si
   toglie. Un push accettato dal servizio push può comunque non arrivare, e il
   servizio non lo sa: per questo restano il gruppo Telegram e il polling della
   pagina.
7. **Fotocamera negata o assente.** La pagina spiega come abilitarla in quel
   browser e ricorda Telegram.
8. **iPhone** può chiedere il permesso della fotocamera a ogni apertura: è un
   limite di iOS, scritto nelle differenze fra test e realtà.

## 8. Test

- **Servizio, veloci.** pytest con il `TestClient` di FastAPI, SQLite in una
  cartella temporanea, orologio iniettato: 48 ore, 12 ore, rinvio e pulizia a
  30 giorni si provano senza aspettare. Telegram e push finti.
- **Pagina, veloci.** `stati.js` con `node --test`.
- **Da capo a fondo.** Poche prove in Chrome vero con la webcam finta
  (`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`).
- **Piano reale** (`tests/reale/`, marcatore `reale`), uno per sistema esterno:
  il bot vero nel gruppo di prova, un push vero verso un browser vero, il
  servizio pubblicato in HTTPS.
- **`docs/differenze-fra-test-e-realta.md`** si scrive prima dei finti. Voci di
  partenza: la webcam dei test è quella finta di Chrome; su iPhone il permesso
  della fotocamera torna a ogni apertura e il push arriva solo all'app aggiunta
  alla schermata Home; nei test il push arriva sempre, nel vero no.

## 9. Messa in produzione

- `docker compose` sulla macchina di Nextcloud; il container ascolta solo su
  `127.0.0.1`. Un volume per SQLite e le foto.
- Un blocco `server` nel Nginx di Alberto per `selfie.esempio.duckdns.org`
  verso il container, con un certificato che copra il sottodominio. Un percorso
  sotto il dominio di Nextcloud si scontrerebbe con le sue rotte.
- Alberto manda `/start` al bot nuovo una volta, altrimenti il bot non può
  scrivergli.
- I link personali si consegnano una volta, in privato.

## 10. Le modifiche a `ctc`

Un modulo nuovo, `giro.py`: il client HTTP del servizio (timeout 5 secondi),
**senza politica**, come `telegram_user.py`. La politica sta dove sta oggi.

1. **Fase 1, dopo la creazione di `Miniatura/` e prima dello scatto dalla
   webcam.** Cerca il giro di stasera: il
   più recente aperto **non prima di un'ora** prima dell'inizio della
   registrazione (un'ora esatta compresa) e non legato a un'altra sessione.
   L'inizio è `recording_started_at`, ricavato dal nome del file di OBS come per
   la finestra di Telegram; è un'ora locale ingenua, da convertire prima del
   confronto come fa `craig.py`. Lo lega alla sessione e registra l'id nello
   stato.
2. **Foto accettate** → `Miniatura/<soprannome>.jpg`, accettate senza altra
   conferma, rivalidate con `validate.py` e scritte con `FsOps`, che non
   sovrascrive mai. Se fra queste c'è quella di `abe`, lo scatto dalla webcam
   si salta, domanda «Pronto per il selfie?» compresa, e il registro lo dice.
   Altrimenti la webcam scatta come oggi: anche quando non c'è un giro, quando
   Alberto non ha scattato e quando il servizio non risponde. Il roster tiene
   `selfie = "webcam"` per `abe`: ora vuol dire «webcam o pagina, mai
   Telegram».
3. **Foto in attesa** → conferma a video, come oggi le foto di Telegram in
   fase 1; chi rifiuta può scrivere un motivo (Invio per nessuno), e l'esito
   torna al servizio con il motivo (`…/esito`). **Da rifare** → la persona
   conta come mancante.
4. **Telegram** si interroga solo per chi non ha una foto della pagina accettata
   o in attesa. Se una foto in attesa diventa «da rifare», alla passata
   successiva quella persona torna fra quelle per cui si guarda Telegram.
5. **Pagina e Telegram per la stessa persona.** Vince la prima foto accettata.
   Una foto dalla pagina che arriva quando `Miniatura/<soprannome>.*` esiste già
   va in `_incerti/` come `<soprannome>-<id giro>-pagina.jpg`: la forma
   `<soprannome>-<numero>-<gruppo>` che `soprannome_da_provvisorio` sa già
   leggere, con `pagina` che deve passare `validate.group_name`. Una volta sola:
   se quel file esiste già in `_incerti/` o in `_scarti/`, non si riscarica. La
   gestisce `ctc fix-selfies`.
6. **Passate successive** (fase 2, `resume`, `solleciti-in-sospeso`): prima di
   Telegram riprendono dal giro legato le foto accettate che in `Miniatura/` non
   ci sono ancora (`selfies.gia_presente`), senza chiedere al servizio cosa è
   già stato consegnato.
   Una foto ancora in attesa alla scadenza della conferma conta come non
   ricevuta: la persona viene sollecitata, come oggi.
7. **Nessun giro stasera** → solo Telegram, e il report lo dice.
8. **Servizio irraggiungibile** → la fase 1 annota e va avanti; la fase 2
   riprova mentre aspetta Craig, legame del giro compreso; se al momento dei solleciti è ancora giù, i
   solleciti partono comunque (un sollecito di troppo si corregge da solo, uno
   mancato costa il selfie), il sollecito stesso lo dice (§10.9) e il report
   avverte che qualcuno può essere stato sollecitato per niente.
9. **Il sollecito dice perché.** I testi a rotazione di oggi restano; sotto,
   una riga per ogni persona sollecitata che ha un motivo, e una riga sola se il
   servizio non rispondeva. I tre casi:
   - foto rifiutata con un motivo: «Per emi la foto non andava: troppo buia.»;
   - foto dalla pagina rimasta senza validazione alla scadenza della conferma:
     «Per emi c'è una foto dalla pagina che non ho ancora guardato: vi do
     conferma.» La conferma arriva in privato (§10.10), non nel gruppo;
   - servizio irraggiungibile: «La pagina dei selfie non rispondeva: chi ha già
     scattato da lì non deve rifarlo.»
   Vale anche per le foto Telegram che Alberto rifiuta in `ctc`, a video o dal
   bot di `ctc`: stesso motivo facoltativo, stessa riga, ma **solo per l'ultima
   foto** di quella persona nella finestra. Se Alberto scarta una foto e ce n'è
   una più recente, la prima può essere semplicemente la foto sbagliata, e non
   c'è niente da spiegare. Con più foto e «nessuna», il motivo riguarda
   l'ultima. Sulla pagina il problema non esiste: ogni persona ha una sola foto
   corrente. Il motivo si legge nel gruppo del party, quindi lo leggono tutti:
   i motivi predefiniti sono neutri di proposito.
10. **La conferma promessa si mantiene, in privato.** Chi ha avuto la riga
    «vi do conferma» finisce, nello stato della sessione, fra le conferme
    promesse. A ogni passata, `solleciti-in-sospeso` chiede al servizio lo
    stato di quelle foto — la stessa chiamata con cui già raccoglie le foto
    accettate (§10.6) — e appena una è validata scrive alla persona in privato,
    con l'account di Alberto, via Telethon:
    - accettata: «Ciao emi, la tua foto va bene, grazie! 📸»;
    - da rifare: «Ciao emi, la tua foto non andava: troppo buia. Me ne mandi
      un'altra? 📸» (senza motivo: «…la tua foto non andava. Me ne mandi
      un'altra? 📸»). Senza «dalla pagina»: può rimandarla anche su Telegram.
    Una volta sola: la promessa si segna come mantenuta nello stato. Vale la
    sicura di `CTC_SOLLECITI`: finché non è armata, il testo va ad Alberto in
    anteprima. Una promessa ancora aperta quando le foto del giro vengono
    cancellate (30 giorni) cade, e il registro lo dice.
    - `telegram_user.py` ha oggi solo `manda_nel_gruppo`: si aggiunge
      `manda_a_persona`. Per scrivere a un identificativo numerico Telethon
      deve aver già incontrato quella persona — di solito perché legge i
      gruppi dove c'è: una convinzione da verificare nel piano reale, non da
      scrivere in un finto.
    - **Il LaunchAgent gira ogni 30 minuti**, oltre che al login, invece che
      solo alle 8:30: altrimenti una foto validata alle 9 aspetterebbe il
      prossimo avvio o il mattino dopo. Resta muto quando non c'è niente da
      fare, e **senza niente in sospeso esce prima di collegarsi** a Telegram
      o al servizio.
11. **Il report** dice da dove viene ogni selfie (pagina, Telegram o webcam) e
    riporta i motivi dei rifiuti.
12. **`ctc doctor`** verifica che il servizio risponda, che il gettone admin sia
    valido, e segnala chi è nel roster ma non sul servizio e chi è sul servizio
    ma non nel roster. `abe` c'è da entrambe le parti: sul servizio come admin.
13. **Piano reale:** `tests/reale/test_giro.py` contro il servizio vero, con un
    gettone e una persona di prova; e il messaggio privato di Telethon verso una
    persona di prova incontrata solo in un gruppo.

## 11. Parametri

| Parametro | Predefinito | Dove |
|---|---|---|
| Rinvio di «Salta» (`RSM_RINVIO_MINUTI`) | 10 minuti | servizio |
| Durata di un giro | 48 ore | servizio |
| Soglia sotto cui «Apri il giro» non riapre | 12 ore | servizio |
| Polling della pagina | 20 secondi | pagina |
| Tentativi automatici di invio | 3 | pagina |
| Dimensione massima di una foto | 8 MB | servizio |
| Cancellazione delle foto | 30 giorni dopo la chiusura del giro | servizio |
| Ciclo del pianificatore | 30 secondi | servizio |
| Cuscinetto prima della registrazione | 1 ora, compresa | `ctc` |
| Timeout verso il servizio | 5 secondi | `ctc` |
| Motivi predefiniti del rifiuto (`RSM_MOTIVI`), ciascuno con etichetta e testo | «Sfocata», «Troppo buia», «Viso non inquadrato», «Tagliata» → «tagliata (controlla che tutta la testa sia ben visibile nella foto)» | servizio, e `ctc` per le foto Telegram |
| Lunghezza massima di un motivo | 200 caratteri | servizio e `ctc` |
| Frequenza del LaunchAgent di `solleciti-in-sospeso` | ogni 30 minuti, e al login | `ctc` |

## 12. Fuori perimetro

- App native (Flutter, Compose) e app iOS da store.
- Validare le foto dalla pagina: Alberto ha Telegram aperto anche sul desktop,
  e il bot basta. Il pannello di master e admin mostra solo nomi e stati.
- Galleria delle foto per il master; più campagne o più tavoli.
- Messaggi privati del bot ai giocatori (un bot non può scrivere a chi non gli
  ha mai scritto): per il singolo giocatore c'è il push.
- Riconoscimento facciale.
- Sincronizzare in automatico la lista persone con il roster di `ctc`: basta
  che `ctc doctor` segnali le differenze.
