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
| Le chiavi di un'iscrizione sono quelle di `chiavi_push()` (`tests/finti.py`): un punto P-256 non compresso di 65 byte e 16 byte di `auth`, in base64url. | Il browser le genera così (`PushSubscription.toJSON()`). Il servizio rifiuta ogni altra forma con un 400: se un browser le mandasse diverse, «Attiva le notifiche» fallirebbe. | `tests/reale/test_push_vero.py`: l'iscrizione vera è passata da `iscrivi`, e il servizio push accetta la cifratura. |
| `pywebpush.webpush` è chiamato con argomenti che registriamo. | `webpush` modifica `vapid_claims` sul posto (ci scrive l'«aud» del primo servizio push) e ha TTL 0 per default: riusare il dizionario firma per il destinatario sbagliato, e un telefono spento perde la notifica. | `tests/test_push.py` (un dizionario nuovo a ogni invio, TTL esplicito) e `tests/reale/test_push_vero.py`. |
| Telegram risponde subito e con `ok: true` (`TelegramFinto`). | Può fallire o rallentare; rifiuta una chat inesistente e non può scrivere a chi non ha mai mandato /start al bot. | `tests/reale/test_telegram_vero.py`. |
| Il bot legge gli aggiornamenti senza concorrenti. | Due programmi che leggono lo stesso bot si rubano gli aggiornamenti (409 Conflict); con un webhook attivo `getUpdates` non funziona. | `tests/reale/test_telegram_vero.py` controlla che non ci sia un webhook. Il bot del servizio è separato da quello di `ctc`. |
| httpx non scrive log. | Al livello INFO httpx scrive l'URL di ogni richiesta, e l'URL di Telegram contiene il token. | `tests/test_app.py` controlla che `costruisci` alzi il livello del logger `httpx`. |
| Il client parla direttamente col servizio (`TestClient`). | In mezzo c'è Nginx, che per default rifiuta i corpi oltre 1 MB con un suo 413. | `tests/reale/test_servizio_pubblicato.py` manda un corpo da 7,5 MB. |
| Il servizio gira su 127.0.0.1, che per il browser è un contesto sicuro. | Fotocamera, service worker e `crypto.subtle` esigono HTTPS con un certificato valido. | `tests/reale/test_servizio_pubblicato.py`. |
| L'orologio è finto e coincide per tutti. | L'orologio del telefono può essere sbagliato. | La pagina misura il rinvio sull'ora del server (`ora` in `/api/stato`), non sulla propria. |
| Nel Chrome dei test la pagina è sempre visibile: la prova simula il passaggio sullo sfondo con `visibilityState`. | Sul telefono la pagina va sullo sfondo a metà conto alla rovescia (una chiamata, un cambio di app): il conto deve fermarsi senza scattare. | Lo stop è provato in Chrome simulando `visibilityState` (`test_pagina_sullo_sfondo_a_meta_conto_ferma_il_conto`); che un telefono vero mandi davvero quell'evento lo si controlla a mano, alla prova generale. |
| Il test node della preferenza del conto usa un archivio finto che ricorda, e uno ostile che lancia; nel Chrome dei test `localStorage` tiene la scelta per tutta la prova. | Safari accetta la scrittura e poi dimentica: ITP cancella i dati di un sito dopo 7 giorni senza visite, e una finestra privata li perde alla chiusura. L'app aggiunta alla schermata Home ha un archivio separato da quello di Safari. Chi gioca ogni settimana resta sotto i 7 giorni, ma una pausa di due settimane spegne l'interruttore. | A mano, su un iPhone. La preferenza è una comodità, non un dato: se sparisce, la pagina riparte da «spento». |

## Da controllare a mano sul telefono

Quello che Chrome con la webcam finta non può dire. Si passa in rassegna alla prova generale, su un iPhone e su un Android.

**Conto alla rovescia**

- iPhone: Centro di controllo, Centro notifiche, banner di chiamata e Siri a metà conto: da verificare se mandano `visibilitychange`. Se lo mandano, il conto si ferma e si torna all'anteprima; se no, il conto va avanti e finisce in revisione (niente parte senza «Invia»). Si annota quale dei due casi avviene per ognuno.
- Blocco dello schermo o cambio di app a metà conto (iPhone e Android): il conto si ferma. Al ritorno non scatta niente in ritardo, e l'anteprima è viva, non congelata.
- Android: la schermata delle app recenti e lo schermo diviso si comportano come il cambio di app.
- iPhone: il numero è centrato e ben visibile sopra il video.
- In orizzontale «Ferma» e «Annulla» restano raggiungibili.
- iPhone: un doppio tocco vero su «Ferma» non ingrandisce la pagina (`touch-action: manipulation`) e la pausa di mezzo secondo basta a non far ripartire il conto.
- Un tocco su «Ferma» nel punto dove stava «Scatta la foto» finisce su «Ferma», non su «Annulla».
- Telefono lento: il ritardo fra «1» e la revisione è accettabile.
- Risparmio energetico: la cadenza 3, 2, 1 resta regolare.
- Mac: si avvia il conto prima di concedere la fotocamera, poi la si nega. Accanto a «Non riesco ad accendere la fotocamera» non compare l'avviso «La fotocamera non è ancora pronta».
- Con Discord aperto il conto non fa nessun suono.
- VoiceOver (iPhone) e TalkBack (Android) annunciano «3», «2», «1», uno alla volta.
- Doppio tocco su «Scatta la foto» con il conto acceso: il conto parte e il secondo tocco cade su «Ferma» e lo ferma, senza scattare niente. È una scelta (il riquadro di «Ferma» coincide con quello di «Scatta la foto»); si controlla che sia così anche col dito.
- «Scatta la foto» sta su una sola riga con i caratteri del telefono (il pulsante è largo `10em`: con un font più largo di quello di Chrome potrebbe andare a capo).

**Cambio di giro**

- Una scheda lasciata aperta sul computer fino al giro dopo, nell'anteprima, nel conto o davanti a una foto da rivedere: quando Alberto apre un giro nuovo (a più di 12 ore dal vecchio), al primo aggiornamento (polling ogni 20 secondi, o ritorno sulla scheda) compare l'invito e la spia della webcam si spegne. Una foto scattata dopo arriva nel giro nuovo. Lo stesso su un telefono lasciato bloccato fino al giro dopo.
