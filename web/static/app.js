// La pagina: collega la macchina a stati (stati.js) al browser.
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
  faseDelGiro,
  fotoPersa,
  leggiPreferenzaConto,
  msAllaFineDelRinvio,
  salvaPreferenzaConto,
  schermata,
  vistaNotifiche,
} from './stati.js';

const gettone = location.pathname.split('/')[2];
const base = `/p/${gettone}/`;
const $ = (id) => document.getElementById(id);

let server = null;
let locale = { ...FASE_INIZIALE };
let giroVisto; // il giro dell'ultimo stato disegnato; indefinito prima del primo
let scarto = 0; // ora del server meno ora del dispositivo, in millisecondi
let flusso = null;
let accensione = null;
let fotoPronta = null;
let timerRinvio = null;
let timerConto = null;
let codifica = false; // allo zero del conto, mentre il JPEG si codifica: il conto è finito
let registrazione = null;
let endpointConfermato = null; // l'iscrizione che il servizio ha salvato in questa sessione della pagina

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

// L'avviso di rete è vero solo finché il servizio non risponde: il primo
// aggiornamento riuscito lo toglie, e lascia stare gli altri avvisi.
const AVVISO_RETE = 'Non riesco a raggiungere il servizio: riprovo tra poco.';
// Descrive l'anteprima dove è comparso (come AVVISO_FOTO_FALLITA): su un'altra schermata non è più vero.
const AVVISO_NON_PRONTA = 'La fotocamera non è ancora pronta: riprova.';
// La codifica della foto non è riuscita (il browser non ha dato un blob, o ha lanciato).
const AVVISO_FOTO_FALLITA = 'Non sono riuscito a fare la foto: riprova.';
const AVVISI_DELL_ANTEPRIMA = [AVVISO_NON_PRONTA, AVVISO_FOTO_FALLITA];
// Dice solo ciò che è verificato: il giro della foto non è più quello attuale, e la foto non si
// può più mandare. Non dice «non è partita» né «prima dell'invio»: dopo un invio non riuscito la
// foto può essere arrivata, con la risposta persa. Parla della foto persa: sparisce quando la
// persona ne comincia una nuova.
const AVVISO_FOTO_PERSA = 'Il giro di questa foto si è chiuso: non si può più mandare.';

async function aggiorna() {
  try {
    server = await api('GET', '/api/stato');
    scarto = Date.parse(server.ora) - Date.now();
  } catch {
    avvisa(AVVISO_RETE);
    return;
  }
  if ($('avviso').textContent === AVVISO_RETE) avvisa('');
  disegna();
}

// Lo stato del servizio adesso, o null se non risponde.
async function statoAttuale() {
  try {
    return await api('GET', '/api/stato');
  } catch {
    return null;
  }
}

// Un doppio tocco manda lo stesso evento due volte: il secondo non è ammesso
// nella fase nuova, e va semplicemente ignorato. Uscendo da riposo la fase annota
// il giro che il servizio mostra in quel momento.
function vai(evento) {
  try {
    locale = dopo(locale, evento, server?.giro?.id ?? null);
  } catch {
    return;
  }
  disegna();
}

function disegna() {
  // La fase locale appartiene al giro in cui è cominciata: se il servizio mostra un
  // giro diverso o nessuno, si riparte da riposo con la foto scartata (non andrebbe
  // mai nel giro nuovo) e la schermata la decide il servizio. Un aggiornamento
  // fallito non passa da qui: `server` resta quello di prima.
  const delGiro = faseDelGiro(locale, server);
  const persa = fotoPersa(locale, delGiro);
  if (delGiro !== locale) {
    fermaTimerConto();
    fotoPronta = null;
    locale = delGiro;
  }
  // Un avviso sul giro vecchio non descrive lo stato di un giro diverso, nemmeno a
  // riposo (nessuna ripartenza, ma il giro è cambiato): quello di rete sì.
  const giroOra = server?.giro?.id ?? null;
  if (server && giroOra !== giroVisto) {
    if (giroVisto !== undefined && $('avviso').textContent !== AVVISO_RETE) avvisa('');
    giroVisto = giroOra;
  }
  // Una foto scattata e non inviata che la ripartenza ha buttato via: lo si dice, dopo la
  // pulizia di sopra (che altrimenti lo cancellerebbe subito). Prende il posto anche dell'avviso
  // di rete: la ripartenza può venire da `vai('fallita')`, che non passa da `aggiorna`, e il
  // messaggio non deve restare muto; l'avviso di rete torna al prossimo aggiornamento fallito.
  if (persa) avvisa(AVVISO_FOTO_PERSA);
  let vista = schermata(server, locale, oraServer());
  // Nello stesso giro il servizio può ancora cambiare stato sotto l'anteprima o il
  // conto (foto accettata): la schermata non è più l'anteprima, si ferma il timer e
  // si torna a riposo. Così allo zero non scatta niente e nessun avviso falso compare.
  if (fotocameraServe() && vista.nome !== 'anteprima') {
    fermaTimerConto();
    locale = dopo(locale, 'annulla');
    vista = schermata(server, locale, oraServer());
  }
  for (const sezione of document.querySelectorAll('[data-schermata]')) {
    sezione.hidden = sezione.dataset.schermata !== vista.nome;
  }
  $('motivo').textContent = vista.motivo ? `: ${vista.motivo}` : '.';
  if (vista.nome !== 'anteprima' && AVVISI_DELL_ANTEPRIMA.includes($('avviso').textContent)) avvisa('');
  if (vista.nome === 'anteprima' && $('avviso').textContent === AVVISO_FOTO_PERSA) avvisa('');
  const inConto = Boolean(vista.conto);
  // Allo zero la foto è già scattata: niente più numero né «Ferma» mentre si codifica.
  // `disegna` riscrive `hidden` a ogni giro, quindi lo stato sta in `codifica`.
  const contaAncora = inConto && !codifica;
  $('numero-conto').hidden = !contaAncora;
  $('scatta-foto').hidden = inConto;
  $('ferma-conto').hidden = !contaAncora;
  $('interruttore-conto').disabled = inConto;
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

// La fotocamera serve nell'anteprima e durante il conto alla rovescia.
const fotocameraServe = () => locale.fase === 'anteprima' || locale.fase === 'conto';

function accendiFotocamera() {
  if (flusso || accensione) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    queueMicrotask(() => vai('negata'));
    return;
  }
  accensione = navigator.mediaDevices
    .getUserMedia({ video: { facingMode: 'user', width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
    .then(async (nuovo) => {
      if (!fotocameraServe()) {
        nuovo.getTracks().forEach((traccia) => traccia.stop());
        return;
      }
      flusso = nuovo;
      const video = $('video');
      video.srcObject = flusso;
      await video.play();
    })
    .catch(() => {
      if (fotocameraServe()) vai('negata');
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
  // La fase di adesso, non il suo nome: durante la codifica la persona può uscire dal
  // conto e cominciarne uno nuovo (anche in un altro giro), e «conto» tornerebbe «conto».
  const inizio = locale;
  const video = $('video');
  if (!video.videoWidth) return false; // la fotocamera non ha ancora un'immagine
  try {
    const tela = $('tela');
    tela.width = video.videoWidth;
    tela.height = video.videoHeight;
    tela.getContext('2d').drawImage(video, 0, 0);
    const blob = await new Promise((risolvi) => tela.toBlob(risolvi, 'image/jpeg', 0.9));
    // Se durante la codifica la persona ha lasciato la fase (Annulla, pagina sullo
    // sfondo, giro cambiato), la foto non serve più: non si va in revisione a cose decise.
    if (locale !== inizio) return false;
    if (!blob) {
      avvisa(AVVISO_FOTO_FALLITA);
      return false;
    }
    fotoPronta = blob;
    $('foto').src = URL.createObjectURL(blob);
  } catch {
    // Il browser può lanciare (memoria, tela troppo grande): la pagina non resta a metà.
    avvisa(AVVISO_FOTO_FALLITA);
    return false;
  }
  vai('scattata');
  return true;
}

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

// Dopo «Ferma» il pulsante dello scatto torna al suo posto: il secondo tocco di un
// doppio tocco lo colpirebbe e farebbe ripartire il conto.
const PAUSA_DOPO_FERMA_MS = 500;
// Non 0: `performance.now()` parte dal caricamento, e con 0 i primi 500 ms ignorerebbero lo scatto.
let fermatoAlle = -Infinity;

function premiScatta() {
  if (performance.now() - fermatoAlle < PAUSA_DOPO_FERMA_MS) return;
  avvisa(''); // un nuovo scatto toglie l'avviso del precedente: non era più vero
  if ($('interruttore-conto').checked) avviaConto();
  else scattaFoto();
}

function avviaConto() {
  let resto = SECONDI_CONTO;
  codifica = false; // una codifica rimasta in sospeso di un conto precedente non conta più
  vai('conta');
  if (locale.fase !== 'conto') return;
  // Il «3» si scrive dopo che `disegna` ha reso visibile la regione aria-live: una
  // regione che appare già piena di solito non viene annunciata dai lettori di schermo.
  $('numero-conto').textContent = String(resto);
  // Il fuoco resta dov'è: spostarlo su «Ferma» lo farebbe premere dall'autoripetizione di Invio.
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
    avvisa(AVVISO_NON_PRONTA);
    return;
  }
  codifica = true;
  disegna(); // toglie il numero e «Ferma» prima dell'attesa: dopo lo zero non c'è più niente da fermare
  const inizio = locale;
  const riuscita = await scattaFoto();
  // Se la fase è cambiata (foto in revisione, Annulla, un conto nuovo già partito) non è più
  // affare di questo scatto: `codifica` e «Ferma» sono di chi c'è adesso. Dopo una foto
  // riuscita `codifica` resta vera, e `avviaConto` la azzera prima di ogni conto.
  if (locale !== inizio) return;
  codifica = false;
  if (!riuscita) vai('ferma');
}

function fermaConto() {
  fermatoAlle = performance.now();
  fermaTimerConto();
  vai('ferma');
}

// «Foto ricevuta» compare solo se il servizio restituisce l'impronta dei byte
// che la pagina ha calcolato: un invio che non torna è un errore, mai un successo.
async function inviaFoto(evento) {
  // Il giro in cui la foto è stata scattata, letto una volta sola: i tentativi
  // automatici non guardano `server`, che nel frattempo può mostrare un giro nuovo.
  const giro = locale.giro;
  vai(evento);
  avvisa('');
  const dati = await fotoPronta.arrayBuffer();
  const attesa = esadecimale(await crypto.subtle.digest('SHA-256', dati));
  try {
    const risposta = await conTentativi(() => api('PUT', `/api/giro/${giro}/foto`, dati, 'image/jpeg'));
    if (risposta.sha256 !== attesa) throw new Error('il servizio ha salvato una foto diversa da quella inviata');
    fotoPronta = null;
    vai('inviata');
    await aggiorna();
  } catch (errore) {
    if (errore.stato === 409 || errore.stato === 410) {
      // Il 409 può arrivare al tentativo automatico dopo un primo invio riuscito:
      // decide la foto che il servizio ha adesso.
      const esito = errore.stato === 409 ? esitoDopoConflitto(await statoAttuale(), attesa) : 'respinta';
      fotoPronta = null;
      vai(esito);
      await aggiorna();
      // Il motivo riguarda la foto di quel giro: se ora il servizio ne mostra un altro, sul suo
      // invito non descriverebbe la schermata. Un 410 con un giro nuovo dice però che la foto è
      // persa, ed è verificato (il servizio stesso ha detto che il giro è chiuso); un 409 no: la
      // foto può essere stata accettata nel giro vecchio, e «persa» sarebbe falso.
      const altroGiro = server?.giro && server.giro.id !== giro;
      if (esito === 'respinta') {
        if (!altroGiro) avvisa(`Foto non inviata: ${errore.message}.`);
        else if (errore.stato === 410) avvisa(AVVISO_FOTO_PERSA);
      }
      return;
    }
    vai('fallita');
    // Se il giro non c'è più la fase è già ripartita da riposo: nessun «Riprova», nessun avviso.
    if (locale.fase === 'errore_invio') avvisa(`Invio non riuscito: ${errore.message}.`);
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

// Il service worker avvisa all'arrivo di un push (sw.js): lo stato nuovo è già
// salvato, e la pagina lo rilegge subito invece di aspettare i 20 secondi.
function ascoltaIlServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.addEventListener('message', (evento) => {
    if (evento.data?.tipo === 'push') aggiorna();
  });
}

const pushPossibile = () => Boolean(registrazione) && 'PushManager' in window && 'Notification' in window;

// Non rifiuta mai: un errore del browser lascia la sezione visibile, e il
// pulsante riprova.
async function disegnaNotifiche() {
  $('suggerimento-ios').hidden = !('standalone' in navigator && !navigator.standalone);
  const possibile = pushPossibile();
  let iscrizione = null;
  if (possibile) {
    try {
      iscrizione = await registrazione.pushManager.getSubscription();
    } catch {
      // senza un'iscrizione leggibile la sezione resta visibile
    }
  }
  const vista = vistaNotifiche({
    possibile,
    permesso: possibile ? Notification.permission : null,
    iscrizioneBrowser: iscrizione !== null,
    confermataDalServizio: iscrizione !== null && iscrizione.endpoint === endpointConfermato,
  });
  $('notifiche').hidden = !vista.sezione;
  $('attiva-notifiche').hidden = !vista.pulsante;
  $('notifiche-testo').textContent = vista.testo ?? '';
}

// Il servizio fa un upsert sull'endpoint: rimandare la stessa iscrizione è innocuo.
async function confermaIscrizione(iscrizione) {
  await api('POST', '/api/push', JSON.stringify(iscrizione.toJSON()), 'application/json');
  endpointConfermato = iscrizione.endpoint;
}

// A ogni caricamento l'iscrizione che il browser ha già torna al servizio, che
// può non averla mai salvata o averla tolta. Non rifiuta mai: se non va, la
// sezione resta visibile e il pulsante riprova.
async function rimandaIscrizione() {
  if (!pushPossibile() || Notification.permission !== 'granted') return;
  try {
    const iscrizione = await registrazione.pushManager.getSubscription();
    if (iscrizione) await confermaIscrizione(iscrizione);
  } catch {
    // resta non confermata
  }
  disegna();
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
    await confermaIscrizione(iscrizione);
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
  $('scatta-foto').addEventListener('click', premiScatta);
  $('annulla').addEventListener('click', () => {
    fermaTimerConto();
    vai('annulla');
  });
  $('ferma-conto').addEventListener('click', fermaConto);
  $('interruttore-conto').addEventListener('change', () => {
    salvaPreferenzaConto(archivioLocale(), $('interruttore-conto').checked);
  });
  $('invia').addEventListener('click', () => inviaFoto('invia'));
  $('rifai').addEventListener('click', () => vai('rifai'));
  $('riprova').addEventListener('click', () => inviaFoto('riprova'));
  $('lascia-perdere').addEventListener('click', lasciaPerdere);
  $('riprova-fotocamera').addEventListener('click', () => vai('riprova'));
  $('annulla-fotocamera').addEventListener('click', () => vai('annulla'));
  $('attiva-notifiche').addEventListener('click', attivaNotifiche);
  $('apri-giro').addEventListener('click', apriGiro);
  document.addEventListener('visibilitychange', () => {
    // Non si scatta una foto che la persona non sta guardando.
    if (document.visibilityState === 'hidden' && locale.fase === 'conto') fermaConto();
    if (document.visibilityState === 'visible') aggiorna();
  });
}

collega();
$('etichetta-conto').textContent = `Conto alla rovescia (${SECONDI_CONTO} secondi)`;
$('interruttore-conto').checked = leggiPreferenzaConto(archivioLocale());
ascoltaIlServiceWorker();
await registraServiceWorker();
rimandaIscrizione(); // non aspetta: la pagina si disegna intanto, e la sezione sparisce alla conferma
await aggiorna();
setInterval(aggiorna, 20000);
