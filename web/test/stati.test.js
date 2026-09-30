import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  FASE_INIZIALE,
  SECONDI_CONTO,
  base64UrlInByte,
  conTentativi,
  dopo,
  esadecimale,
  esitoApertura,
  esitoDopoConflitto,
  faseDelGiro,
  leggiPreferenzaConto,
  msAllaFineDelRinvio,
  salvaPreferenzaConto,
  schermata,
  vistaNotifiche,
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

test('la richiesta di un\'altra foto vince sul rinvio ancora in corso', () => {
  // Salta, poi «Scatta adesso», poi Alberto chiede un'altra foto entro i 10 minuti.
  const s = stato({
    foto: { stato: 'da_rifare', sha256: 'x', motivo: 'sfocata' },
    rinvio_fino_a: '2026-10-04T20:05:00+00:00',
  });
  assert.deepEqual(schermata(s, FASE_INIZIALE, ORA), { nome: 'nuova_richiesta', motivo: 'sfocata' });
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

test('un 409 dopo una risposta persa è un successo solo se il servizio ha proprio quella foto', () => {
  const accettata = stato({ foto: { stato: 'accettata', sha256: 'abc', motivo: null } });
  assert.equal(esitoDopoConflitto(accettata, 'abc'), 'inviata');
  assert.equal(esitoDopoConflitto(accettata, 'def'), 'respinta');
  assert.equal(esitoDopoConflitto(stato(), 'abc'), 'respinta');
  assert.equal(esitoDopoConflitto(null, 'abc'), 'respinta'); // il servizio non ha risposto: niente da verificare
  assert.equal(esitoDopoConflitto(stato({ foto: { stato: 'accettata', motivo: null } }), undefined), 'respinta');
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

test('le notifiche si danno per attive solo dopo la conferma del servizio', () => {
  const attive = { possibile: true, permesso: 'granted', iscrizioneBrowser: true, confermataDalServizio: true };
  const invito = { sezione: true, pulsante: true, testo: "Vuoi ricevere l'invito anche a pagina chiusa?" };
  assert.deepEqual(vistaNotifiche(attive), { sezione: false, pulsante: false, testo: null });
  // permesso e iscrizione del browser non bastano: il rinvio al servizio può essere fallito
  assert.deepEqual(vistaNotifiche({ ...attive, confermataDalServizio: false }), invito);
  assert.deepEqual(vistaNotifiche({ ...attive, iscrizioneBrowser: false }), invito);
  assert.deepEqual(vistaNotifiche({ ...attive, permesso: 'default' }), invito);
});

test('le notifiche bloccate o impossibili', () => {
  const niente = { possibile: false, permesso: null, iscrizioneBrowser: false, confermataDalServizio: false };
  assert.deepEqual(vistaNotifiche(niente), { sezione: false, pulsante: false, testo: null });
  assert.deepEqual(vistaNotifiche({ ...niente, possibile: true, permesso: 'denied' }), {
    sezione: true,
    pulsante: false,
    testo: 'Le notifiche sono bloccate: si riattivano dalle impostazioni del browser.',
  });
});

test('base64url in byte, con e senza padding', () => {
  assert.deepEqual([...base64UrlInByte('AQID')], [1, 2, 3]);
  assert.deepEqual([...base64UrlInByte('-_8')], [251, 255]);
});

test('esadecimale', () => {
  assert.equal(esadecimale(new Uint8Array([0, 15, 255]).buffer), '000fff');
});

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

// La fase locale appartiene al giro in cui è cominciata (spec §3.3): se il servizio
// mostra un giro diverso, o nessuno, la pagina riparte dall'invito.
const GIRO_NUOVO = { ...GIRO, id: 2 };
const nel_giro = (fase, giro = GIRO.id) => ({ fase, giro });
const FASI_DI_UN_GIRO = ['anteprima', 'conto', 'revisione', 'errore_invio', 'fotocamera_negata'];

test('uscendo da riposo si annota il giro, e la fase lo tiene fino al ritorno a riposo', () => {
  assert.deepEqual(FASE_INIZIALE, { fase: 'riposo', giro: null });
  let locale = dopo(FASE_INIZIALE, 'scatta', 7);
  assert.deepEqual(locale, { fase: 'anteprima', giro: 7 });
  // Il giro del servizio può cambiare mentre la persona è nell'anteprima: l'annotazione no.
  for (const [evento, fase] of [['conta', 'conto'], ['scattata', 'revisione'], ['invia', 'invio'], ['fallita', 'errore_invio']]) {
    locale = dopo(locale, evento, 8);
    assert.deepEqual(locale, { fase, giro: 7 }, `dopo «${evento}»`);
  }
  assert.deepEqual(dopo(locale, 'lascia_perdere', 8), { fase: 'riposo', giro: null });
});

test('una fase dello stesso giro resta com\'è', () => {
  for (const fase of [...FASI_DI_UN_GIRO, 'invio']) {
    const locale = nel_giro(fase);
    assert.equal(faseDelGiro(locale, stato()), locale, fase);
  }
});

test('se il giro cambia la pagina riparte da riposo, in ogni fase tranne l\'invio', () => {
  for (const fase of FASI_DI_UN_GIRO) {
    assert.equal(faseDelGiro(nel_giro(fase), stato({ giro: GIRO_NUOVO })), FASE_INIZIALE, fase);
  }
});

test('se il giro non c\'è più la pagina riparte da riposo', () => {
  for (const fase of FASI_DI_UN_GIRO) {
    assert.equal(faseDelGiro(nel_giro(fase), stato({ giro: null })), FASE_INIZIALE, fase);
    assert.equal(faseDelGiro(nel_giro(fase), null), FASE_INIZIALE, fase); // il servizio non ha mai risposto
  }
});

test('un invio in volo non si interrompe, anche se il giro è cambiato', () => {
  const locale = nel_giro('invio');
  assert.equal(faseDelGiro(locale, stato({ giro: GIRO_NUOVO })), locale);
  assert.equal(faseDelGiro(locale, stato({ giro: null })), locale);
});

test('finito l\'invio, un invio non riuscito di un giro che non c\'è più riparte da riposo', () => {
  const dopo_l_invio = dopo(nel_giro('invio'), 'fallita');
  assert.deepEqual(dopo_l_invio, nel_giro('errore_invio'));
  assert.equal(faseDelGiro(dopo_l_invio, stato({ giro: GIRO_NUOVO })), FASE_INIZIALE);
  assert.equal(faseDelGiro(dopo_l_invio, stato()), dopo_l_invio); // nello stesso giro resta «Riprova»
});

test('riposo resta riposo, con qualunque stato del servizio', () => {
  for (const server of [stato(), stato({ giro: GIRO_NUOVO }), stato({ giro: null }), null]) {
    assert.equal(faseDelGiro(FASE_INIZIALE, server), FASE_INIZIALE);
  }
});
