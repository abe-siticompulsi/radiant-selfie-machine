// Il service worker della pagina personale. Il suo ambito è /p/<gettone>/:
// al tocco sulla notifica apre proprio quella pagina, senza che il servizio
// debba conoscere il gettone. Il carico utile è {"titolo", "testo"} (push.py).
// Oltre a mostrare la notifica, avvisa la pagina aperta, che rilegge lo stato.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

// Le finestre aperte di questa persona: quelle il cui indirizzo comincia con
// l'ambito del service worker, /p/<gettone>/. Le altre pagine della stessa
// origine (un'altra persona sullo stesso browser) non c'entrano.
async function finestreDellaPersona() {
  const finestre = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  return finestre.filter((finestra) => finestra.url.startsWith(self.registration.scope));
}

// Il servizio manda il push dopo aver salvato lo stato: la pagina aperta lo
// rilegge subito, senza aspettare il controllo dei 20 secondi.
async function avvisaLePagine() {
  for (const finestra of await finestreDellaPersona()) finestra.postMessage({ tipo: 'push' });
}

self.addEventListener('push', (evento) => {
  let dati = { titolo: 'Radiant Selfie Machine', testo: '' };
  try {
    dati = evento.data.json();
  } catch {
    // un push senza JSON mostra comunque il titolo
  }
  // La notifica compare comunque, anche con la pagina davanti: Chrome e Safari
  // chiedono che ogni push ne mostri una. Un errore in una delle due cose non
  // ferma l'altra.
  evento.waitUntil(
    Promise.allSettled([
      self.registration.showNotification(dati.titolo, {
        body: dati.testo,
        icon: '/static/icona-192.png',
        tag: 'radiant-selfie-machine',
        renotify: true,
      }),
      avvisaLePagine(),
    ]),
  );
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil(
    (async () => {
      const [finestra] = await finestreDellaPersona();
      if (finestra) return finestra.focus();
      return self.clients.openWindow(self.registration.scope);
    })(),
  );
});
