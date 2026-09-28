// Il service worker della pagina personale. Il suo ambito è /p/<gettone>/:
// al tocco sulla notifica apre proprio quella pagina, senza che il servizio
// debba conoscere il gettone. Il carico utile è {"titolo", "testo"} (push.py).

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

self.addEventListener('push', (evento) => {
  let dati = { titolo: 'Radiant Selfie Machine', testo: '' };
  try {
    dati = evento.data.json();
  } catch {
    // un push senza JSON mostra comunque il titolo
  }
  evento.waitUntil(
    self.registration.showNotification(dati.titolo, {
      body: dati.testo,
      icon: '/static/icona-192.png',
      tag: 'radiant-selfie-machine',
      renotify: true,
    }),
  );
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil(
    (async () => {
      const finestre = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const finestra of finestre) {
        if (finestra.url.startsWith(self.registration.scope)) return finestra.focus();
      }
      return self.clients.openWindow(self.registration.scope);
    })(),
  );
});
