# Messa in produzione

Sulla macchina di Nextcloud (AIO, x86_64), dietro il proxy di Alberto (Nginx
Proxy Manager, o un Nginx scritto a mano). Una
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

Compila `config/rsm.env`: token del bot, contatto VAPID e il tuo
identificativo Telegram in `RSM_ADMIN_TELEGRAM_ID` (il numero positivo; se non
lo sai, te lo dice il comando qui sotto, dopo il `/start` in privato del punto
1). **Lascia `RSM_GRUPPO` vuoto**: è la sicura.

Poi l'identificativo del gruppo di prova. Il bot nasce con la privacy attiva:
nel gruppo non riceve i messaggi normali, solo i comandi rivolti a lui. Scrivi
quindi nel gruppo `/start@<nome_del_bot>` (il nome utente del bot, quello che
finisce in `bot`) e, sul server, prima di avviare il servizio (acceso, si
prenderebbe lui gli aggiornamenti):

```bash
TOKEN=$(grep -oP '^RSM_BOT_TOKEN=\K.*' config/rsm.env)
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | grep -o '"chat":{"id":-\?[0-9]*' | sort -u
unset TOKEN
```

Il numero negativo è il gruppo e va in `RSM_GRUPPO_PROVA`; quello positivo sei
tu, in privato, e va in `RSM_ADMIN_TELEGRAM_ID`.

## 4. La chiave VAPID

`config` è montata in sola lettura nel servizio: per generare la chiave si
monta una seconda volta, scrivibile, solo per questo comando.

```bash
docker compose build rsm
docker compose run --rm --no-deps -v "$PWD/config:/nuova" rsm rsm vapid genera /nuova/vapid.pem
```

Il file nasce con i permessi 600. Non va rigenerato: una chiave nuova rende
inutili tutte le iscrizioni push già fatte.

## 5. Il proxy e il certificato

Il sottodominio risolve già all'indirizzo della macchina (DuckDNS risolve ogni
sottodominio). Il servizio ascolta solo su `127.0.0.1:8470` (`compose.yaml`):
nessuna porta aperta verso fuori, ci arriva solo il proxy. Due strade, a
seconda del proxy.

`client_max_body_size` serve in entrambe. Nginx, per default, rifiuta i corpi
oltre 1 MB, e la foto vera fallirebbe con un 413 di Nginx, non nostro. Con 9 MB
il limite resta appena sopra gli 8 MB che il servizio accetta.

### Con Nginx Proxy Manager

Prima di tutto, guarda in che rete gira NPM:

```bash
docker inspect NOME_DEL_CONTAINER_DI_NPM --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

(il nome del container lo dà `docker ps --format '{{.Names}}\t{{.Image}}' | grep -i proxy`).

**Rete `host`** (`network_mode: host`): NPM vede la rete del server, e per lui
`127.0.0.1` è il server stesso. Non serve nient'altro. Nuovo «Proxy Host»:

| Scheda | Campo | Valore |
|---|---|---|
| Details | Domain Names | `selfie.esempio.duckdns.org` |
| Details | Scheme | `http` |
| Details | Forward Hostname / IP | `127.0.0.1` |
| Details | Forward Port | `8470` |
| Details | Cache Assets | spento |
| Details | Block Common Exploits | spento |
| Details | Websockets Support | spento |
| Details | Access List | Publicly Accessible |
| SSL | SSL Certificate | Request a new SSL Certificate |
| SSL | Force SSL, HTTP/2 Support | accesi |
| SSL | HSTS | a scelta; «HSTS Subdomains» spento |
| Advanced | Custom Nginx Configuration | `client_max_body_size 9m;` |

Perché così:
- **Cache Assets spento.** Acceso, NPM terrebbe in cache `app.js` e gli altri
  file statici: dopo un aggiornamento i telefoni userebbero il JavaScript
  vecchio. Il servizio manda `no-cache` proprio per questo.
- **Block Common Exploits spento.** A questo servizio non serve, e così non
  blocca per sbaglio le richieste di `ctc`.
- **Access List pubblica.** Le pagine le proteggono i link personali.
- **Certificato.** La verifica HTTP funziona se la porta 80 arriva a NPM, come
  per Nextcloud. Altrimenti «Use a DNS Challenge», con il provider DuckDNS e il
  tuo token DuckDNS.
- **Intestazioni.** `Host` e `X-Forwarded-Proto` NPM le mette da solo; i link,
  comunque, il servizio li costruisce da `RSM_URL_BASE`.

**Un'altra rete** (NPM in una rete Docker sua): `127.0.0.1` sarebbe il container
di NPM, e il proxy risponderebbe 502. Si mette il servizio anche nella rete di
NPM con un `compose.override.yaml` accanto a `compose.yaml`, che Docker Compose
legge da solo e che resta solo sul server:

```yaml
services:
  rsm:
    networks:
      default: {}
      npm:
        aliases: [radiant-selfie]

networks:
  npm:
    external: true
    name: NOME_DELLA_RETE_DI_NPM
```

Nel proxy host, allora, Forward Hostname `radiant-selfie` e Forward Port `8000`
(la porta dentro il container); il resto come nella tabella. Con la rete `host`
questo file non va creato: Docker rifiuta un container nella rete `host`
insieme ad altre reti.

### Con un Nginx scritto a mano

Prima il certificato: il blocco qui sotto lo cita, e finché i file non
esistono `nginx -t` fallisce. Con certbot:

```bash
certbot certonly --nginx -d selfie.esempio.duckdns.org
```

oppure con `certbot certonly --webroot`, o con il metodo che già usi per
Nextcloud.

Poi un blocco nuovo, accanto a quello di Nextcloud, con il
`client_max_body_size` detto sopra.

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
curl -fsS http://127.0.0.1:8470/salute
curl -fsS https://selfie.esempio.duckdns.org/salute
```

Atteso: `{"ok":true}` da tutti e due. Il primo interroga il servizio
direttamente, il secondo passa dal proxy: se risponde solo il primo, il
problema è nel proxy o nel certificato.

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

Se la serata vera cade a meno di 12 ore dall'apertura del giro di prova,
chiudilo: «Apri il giro» lo riuserebbe, con le foto di prova dentro (e una foto
accettata è definitiva).

```bash
docker compose exec rsm rsm giro chiudi
```

Dice quale giro ha chiuso e chi l'aveva aperto, oppure che non c'era un giro
aperto. Le pagine mostrano «Nessun giro aperto» alla prossima rilettura. Se
proprio in quell'istante qualcuno ha premuto «Apri il giro», il comando lo dice e
dice quale giro è aperto adesso: non rilanciarlo, chiuderebbe il giro della serata.

## 9. Armare la sicura

Solo dopo la prova generale: scrivi l'identificativo del party in `RSM_GRUPPO`
dentro `config/rsm.env`, poi `docker compose up -d`. La risposta a «Apri il
giro» passerà da «gruppo di prova» a «gruppo del party».

## Aggiornare

```bash
git pull && docker compose up -d --build
```
