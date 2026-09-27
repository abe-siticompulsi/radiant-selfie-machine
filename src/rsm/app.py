"""Le rotte HTTP. Sottili: autenticano, chiamano il servizio, traducono.

Un gettone assente, sconosciuto o con il ruolo sbagliato riceve 404, come una
pagina che non esiste. Ciò che non serve alla risposta (push, messaggi del bot)
va nei `BackgroundTasks`, che girano dopo che la risposta è partita: la pagina
non aspetta Telegram, e `ctc` non va in timeout per colpa sua.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import foto, regole
from .servizio import ErroreServizio, Servizio
from .store import Persona

CSP = (
    "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
    "connect-src 'self'; script-src 'self'; style-src 'self'; manifest-src 'self'; "
    "worker-src 'self'; base-uri 'none'; frame-ancestors 'none'"
)


def crea_app(servizio: Servizio, *, cartella_web: Path, lifespan=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=cartella_web / "static"), name="static")

    @app.exception_handler(ErroreServizio)
    async def _errore_servizio(_richiesta: Request, errore: ErroreServizio) -> JSONResponse:
        return JSONResponse({"errore": str(errore)}, status_code=errore.codice)

    @app.exception_handler(foto.FotoRifiutata)
    async def _foto_rifiutata(_richiesta: Request, errore: foto.FotoRifiutata) -> JSONResponse:
        return JSONResponse({"errore": str(errore)}, status_code=errore.codice)

    def persona_dal_gettone(gettone: str) -> Persona:
        persona = servizio.persona(gettone)
        if persona is None:
            raise HTTPException(status_code=404)
        return persona

    def persona_della_pagina(gettone: str) -> Persona:
        persona = persona_dal_gettone(gettone)
        if persona.ruolo not in regole.CHI_SCATTA:
            raise HTTPException(status_code=404)
        return persona

    def persona_richiesta(authorization: str | None = Header(default=None)) -> Persona:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=404)
        return persona_dal_gettone(authorization.removeprefix("Bearer ").strip())

    def ruoli(*ammessi: str):
        def dipendenza(persona: Persona = Depends(persona_richiesta)) -> Persona:
            if persona.ruolo not in ammessi:
                raise HTTPException(status_code=404)
            return persona

        return dipendenza

    chi_scatta = ruoli(*regole.CHI_SCATTA)
    chi_apre = ruoli(*regole.CHI_APRE)
    solo_ctc = ruoli(regole.CTC)

    @app.get("/salute")
    def salute() -> dict:
        return {"ok": True}

    # --- la pagina personale

    @app.get("/p/{gettone}")
    def pagina_senza_barra(gettone: str) -> RedirectResponse:
        persona_della_pagina(gettone)
        return RedirectResponse(f"/p/{gettone}/", status_code=308)

    @app.get("/p/{gettone}/")
    def pagina(gettone: str) -> FileResponse:
        persona_della_pagina(gettone)
        return FileResponse(
            cartella_web / "index.html",
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": CSP,
            },
        )

    @app.get("/p/{gettone}/manifest.webmanifest")
    def manifest(gettone: str) -> JSONResponse:
        persona_della_pagina(gettone)
        base = f"/p/{gettone}/"
        return JSONResponse(
            {
                "name": "Radiant Selfie Machine",
                "short_name": "Selfie",
                "start_url": base,
                "scope": base,
                "display": "standalone",
                "background_color": "#1b1030",
                "theme_color": "#2b1a4a",
                "icons": [
                    {"src": "/static/icona-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icona-512.png", "sizes": "512x512", "type": "image/png"},
                ],
            },
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/p/{gettone}/sw.js")
    def service_worker(gettone: str) -> FileResponse:
        persona_della_pagina(gettone)
        return FileResponse(
            cartella_web / "sw.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    # --- la pagina

    @app.get("/api/stato")
    def stato(persona: Persona = Depends(persona_richiesta)) -> dict:
        return servizio.stato(persona)

    @app.post("/api/giro")
    def apri_giro(background: BackgroundTasks, persona: Persona = Depends(chi_apre)) -> dict:
        risposta = servizio.apri_giro(persona)
        if risposta["nuovo"]:
            background.add_task(servizio.invita, persona.soprannome)
        return risposta

    @app.put("/api/giro/{giro_id}/foto")
    async def carica_foto(
        giro_id: int,
        richiesta: Request,
        background: BackgroundTasks,
        persona: Persona = Depends(chi_scatta),
    ) -> dict:
        dichiarati = richiesta.headers.get("content-length", "")
        if dichiarati.isdigit() and int(dichiarati) > foto.MASSIMO:
            raise foto.FotoTroppoGrande(f"la foto supera gli {foto.MASSIMO} byte")
        dati = bytearray()
        async for pezzo in richiesta.stream():
            dati.extend(pezzo)
            if len(dati) > foto.MASSIMO:
                raise foto.FotoTroppoGrande(f"la foto supera gli {foto.MASSIMO} byte")
        ricevuta = await run_in_threadpool(servizio.ricevi_foto, persona, giro_id, bytes(dati))
        if ricevuta.foto.stato == regole.IN_ATTESA:
            background.add_task(
                servizio.annuncia_foto,
                giro_id,
                persona.soprannome,
                ricevuta.foto.versione,
                ricevuta.messaggio_da_ritirare,
            )
        return {
            "sha256": ricevuta.foto.sha256,
            "byte": ricevuta.foto.byte,
            "stato": ricevuta.foto.stato,
            "versione": ricevuta.foto.versione,
        }

    @app.post("/api/giro/{giro_id}/rinvio")
    def rinvia(giro_id: int, persona: Persona = Depends(chi_scatta)) -> dict:
        return {"fino_a": servizio.rinvia(persona, giro_id).isoformat()}

    @app.post("/api/push", status_code=204)
    def iscrivi(dati: dict = Body(...), persona: Persona = Depends(chi_scatta)) -> Response:
        servizio.iscrivi(persona, dati)
        return Response(status_code=204)

    @app.delete("/api/push", status_code=204)
    def disiscrivi(dati: dict = Body(...), persona: Persona = Depends(chi_scatta)) -> Response:
        servizio.disiscrivi(persona, str(dati.get("endpoint", "")))
        return Response(status_code=204)

    # --- ctc

    @app.get("/api/giri")
    def giri(dal: datetime, _ctc: Persona = Depends(solo_ctc)) -> list[dict]:
        # «dal» arriva nella query: il «+» del fuso va codificato (%2B), e httpx
        # lo fa da solo con `params=`. Una data senza fuso è ambigua: 400.
        if dal.tzinfo is None:
            raise HTTPException(status_code=400, detail="«dal» deve avere il fuso orario")
        return servizio.giri_dal(dal)

    @app.post("/api/giro/{giro_id}/lega")
    def lega(giro_id: int, dati: dict = Body(...), _ctc: Persona = Depends(solo_ctc)) -> dict:
        return servizio.lega(giro_id, str(dati.get("sessione", "")))

    @app.get("/api/giro/{giro_id}/foto")
    def elenco_foto(giro_id: int, _ctc: Persona = Depends(solo_ctc)) -> list[dict]:
        return servizio.foto_del_giro(giro_id)

    @app.get("/api/giro/{giro_id}/foto/{soprannome}")
    def scarica_foto(giro_id: int, soprannome: str, _ctc: Persona = Depends(solo_ctc)) -> Response:
        return Response(
            servizio.dati_foto(giro_id, soprannome),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/giro/{giro_id}/foto/{soprannome}/esito")
    def esito(
        giro_id: int,
        soprannome: str,
        background: BackgroundTasks,
        dati: dict = Body(...),
        _ctc: Persona = Depends(solo_ctc),
    ) -> dict:
        versione = dati.get("versione")
        if not isinstance(versione, int) or isinstance(versione, bool):
            raise HTTPException(status_code=400, detail="«versione» mancante")
        motivo = dati.get("motivo")
        if motivo is not None and not isinstance(motivo, str):
            raise HTTPException(status_code=400, detail="«motivo» deve essere un testo")
        decisa = servizio.decidi(giro_id, soprannome, versione, str(dati.get("esito", "")), motivo)
        background.add_task(servizio.dopo_decisione, decisa)
        return {"stato": decisa.stato, "motivo": decisa.motivo, "versione": decisa.versione}

    @app.get("/api/persone")
    def persone(_ctc: Persona = Depends(solo_ctc)) -> list[dict]:
        return servizio.persone()

    return app
