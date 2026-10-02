# Radiant Selfie Machine

La pagina web con cui chi siede al tavolo dei *Danni Radiosi* scatta il selfie
per la miniatura quando il master apre il giro, e il servizio che lo raccoglie
per `close-the-circle`. Alberto valida ogni foto dal bot Telegram.

Il design sta in `docs/superpowers/specs/`, il piano in `docs/superpowers/plans/`.
Leggi la specifica prima di cambiare il comportamento: molte scelte hanno un
motivo che il codice da solo non spiega.

## Sviluppo

Richiede [uv](https://docs.astral.sh/uv/), Node (per i test della pagina) e
Chrome (per le prove da capo a fondo).

```bash
uv sync
uv run pytest -q                      # la suite veloce
node --test "web/test/*.test.js"      # la macchina a stati della pagina
uv run pytest -m e2e -q               # tre prove in Chrome con la webcam finta
uv run ruff check src tests strumenti
```

Il piano reale (`-m reale`) si lancia sul server, contro i sistemi veri: v.
`docs/messa-in-produzione.md`. Le convinzioni che i finti mettono per iscritto,
e dove vengono verificate, stanno in `docs/differenze-fra-test-e-realta.md`.

## In produzione

Sulla macchina di Nextcloud, in Docker, dietro Nginx Proxy Manager o Nginx:
`docs/messa-in-produzione.md`. Finché `RSM_GRUPPO` è vuoto, il bot annuncia il
giro nel gruppo di prova.
