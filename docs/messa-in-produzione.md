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

Poi l'identificativo del gruppo di prova. Il bot nasce con la privacy attiva:
nel gruppo non riceve i messaggi normali, solo i comandi rivolti a lui. Scrivi
quindi nel gruppo `/start@<nome_del_bot>` (il nome utente del bot, quello che
finisce in `bot`) e, sul server, prima di avviare il servizio (acceso, si
prenderebbe lui gli aggiornamenti):

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

Il sottodominio risolve già all'indirizzo della macchina (DuckDNS risolve ogni
sottodominio). Prima il certificato: il blocco qui sotto lo cita, e finché i
file non esistono `nginx -t` fallisce. Con certbot:

```bash
certbot certonly --nginx -d selfie.esempio.duckdns.org
```

oppure con `certbot certonly --webroot`, o con il metodo che già usi per
Nextcloud.

Poi un blocco nuovo, accanto a quello di Nextcloud. `client_max_body_size` è
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

`http2 on;` esiste da Nginx 1.25.1 (`nginx -v` dice la versione): con un Nginx
precedente si scrive `listen 443 ssl http2;` e si toglie la riga `http2 on;`.
Poi:

```bash
nginx -t && systemctl reload nginx
```

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
