// La macchina a stati della pagina. Non tocca il browser: si prova con
//   node --test "web/test/*.test.js"
//
// `schermata` decide cosa mostrare a partire dallo stato del servizio e dalla
// fase locale (quello che la persona sta facendo adesso); `dopo` fa avanzare la
// fase locale e rifiuta un evento che in quella fase non ha senso.

export const FASE_INIZIALE = Object.freeze({ fase: 'riposo' });

const TRANSIZIONI = {
  riposo: { scatta: 'anteprima' },
  anteprima: { scattata: 'revisione', conta: 'conto', negata: 'fotocamera_negata', annulla: 'riposo' },
  conto: { scattata: 'revisione', ferma: 'anteprima', annulla: 'riposo', negata: 'fotocamera_negata' },
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
  // Il conto alla rovescia si mostra come anteprima con il numero sopra: se fosse
  // una schermata a parte, la fotocamera si spegnerebbe proprio prima dello scatto.
  if (locale.fase === 'conto') return { nome: 'anteprima', conto: true };
  if (FASI_CHE_VINCONO.has(locale.fase)) return { nome: locale.fase };
  if (foto?.stato === 'in_attesa') return { nome: 'in_attesa' };
  // Prima del rinvio: una richiesta arrivata dopo un «Salta» è la notizia più recente.
  if (foto?.stato === 'da_rifare') return { nome: 'nuova_richiesta', motivo: foto.motivo ?? null };
  if (msAllaFineDelRinvio(server, oraMs) !== null) return { nome: 'rinviato' };
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

// Un 409 al tentativo automatico può seguire un primo invio riuscito la cui
// risposta si è persa (la foto di Alberto è accettata all'arrivo, o quella di un
// giocatore è stata accettata nel frattempo). È un successo solo se la foto che
// il servizio ha adesso è proprio quella che la pagina ha mandato: stesso
// evento di un invio riuscito, altrimenti quello di un invio respinto.
export function esitoDopoConflitto(server, impronta) {
  return impronta && server?.foto?.sha256 === impronta ? 'inviata' : 'respinta';
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

// La sezione «Attiva le notifiche». Il permesso e l'iscrizione del browser non
// dicono che i push arriveranno: il servizio può non averla salvata, o averla
// tolta. La sezione sparisce solo quando il servizio ha confermato l'iscrizione
// in questa sessione della pagina.
export function vistaNotifiche({ possibile, permesso, iscrizioneBrowser, confermataDalServizio }) {
  if (!possibile) return { sezione: false, pulsante: false, testo: null };
  if (permesso === 'denied') {
    return {
      sezione: true,
      pulsante: false,
      testo: 'Le notifiche sono bloccate: si riattivano dalle impostazioni del browser.',
    };
  }
  if (permesso === 'granted' && iscrizioneBrowser && confermataDalServizio) {
    return { sezione: false, pulsante: false, testo: null };
  }
  return { sezione: true, pulsante: true, testo: "Vuoi ricevere l'invito anche a pagina chiusa?" };
}

export function base64UrlInByte(testo) {
  const base64 = testo.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (testo.length % 4)) % 4);
  return Uint8Array.from(atob(base64), (carattere) => carattere.charCodeAt(0));
}

export function esadecimale(buffer) {
  return Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, '0')).join('');
}

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
