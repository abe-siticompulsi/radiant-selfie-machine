import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  FASE_INIZIALE,
  base64UrlInByte,
  conTentativi,
  dopo,
  esadecimale,
  esitoApertura,
  esitoDopoConflitto,
  msAllaFineDelRinvio,
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
