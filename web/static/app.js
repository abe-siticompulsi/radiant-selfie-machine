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

// L'avviso di rete è vero solo finché il servizio non risponde: il primo
// aggiornamento riuscito lo toglie, e lascia stare gli altri avvisi.
const AVVISO_RETE = 'Non riesco a raggiungere il servizio: riprovo tra poco.';

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
