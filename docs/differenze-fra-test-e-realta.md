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
