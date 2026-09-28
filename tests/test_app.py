import logging

import pytest
from fastapi.testclient import TestClient
from py_vapid import Vapid

from rsm import foto
from rsm.app import CSP, crea_app
from rsm.principale import costruisci
from tests.finti import chiavi_push
from tests.immagini import jpeg, png


@pytest.fixture
def cartella_web(tmp_path):
    web = tmp_path / "web"
    (web / "static").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>pagina</title>")
    (web / "sw.js").write_text("// service worker")
    (web / "static" / "stati.js").write_text("export {};")
    return web


@pytest.fixture
def client(servizio, cartella_web):
    return TestClient(crea_app(servizio, cartella_web=cartella_web))


def con(persone, soprannome):
    return {"Authorization": f"Bearer {persone[soprannome][1]}"}


def apri(client, persone):
    return client.post("/api/giro", headers=con(persone, "gio")).json()["giro"]["id"]


def test_salute(client):
    assert client.get("/salute").json() == {"ok": True}


def test_senza_gettone_o_con_uno_sbagliato_404(client):
    assert client.get("/api/stato").status_code == 404
    assert client.get("/api/stato", headers={"Authorization": "Bearer inventato"}).status_code == 404
    assert client.get("/api/stato", headers={"Authorization": "Basic x"}).status_code == 404


def test_lo_stato(client, persone):
    risposta = client.get("/api/stato", headers=con(persone, "emi"))
    assert risposta.status_code == 200
    assert risposta.json()["persona"] == "emi"


def test_la_pagina_personale(client, persone):
    gettone = persone["emi"][1]
    senza_barra = client.get(f"/p/{gettone}", follow_redirects=False)
    assert senza_barra.status_code == 308
    assert senza_barra.headers["location"] == f"/p/{gettone}/"
    pagina = client.get(f"/p/{gettone}/")
    assert pagina.status_code == 200
    assert "pagina" in pagina.text
    assert pagina.headers["content-security-policy"] == CSP
    assert pagina.headers["cache-control"] == "no-store"
    assert pagina.headers["referrer-policy"] == "no-referrer"
    assert client.get("/p/inventato/").status_code == 404
    assert client.get("/p/inventato", follow_redirects=False).status_code == 404
    assert client.get(f"/p/{persone['ctc'][1]}/").status_code == 404


def test_manifest_e_service_worker_della_persona(client, persone):
    gettone = persone["emi"][1]
    manifest = client.get(f"/p/{gettone}/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.json()["start_url"] == f"/p/{gettone}/"
    assert manifest.json()["scope"] == f"/p/{gettone}/"
    sw = client.get(f"/p/{gettone}/sw.js")
    assert sw.headers["content-type"].startswith("text/javascript")
    assert client.get("/p/inventato/sw.js").status_code == 404


def test_il_gettone_di_ctc_non_apre_la_pagina(client, persone):
    gettone = persone["ctc"][1]
    assert client.get(f"/p/{gettone}", follow_redirects=False).status_code == 404
    assert client.get(f"/p/{gettone}/").status_code == 404
    assert client.get(f"/p/{gettone}/manifest.webmanifest").status_code == 404
    assert client.get(f"/p/{gettone}/sw.js").status_code == 404


def test_i_file_statici(client):
    assert client.get("/static/stati.js").status_code == 200


def test_aprire_il_giro(client, persone, notifiche, telegram):
    assert client.post("/api/giro", headers=con(persone, "emi")).status_code == 404
    risposta = client.post("/api/giro", headers=con(persone, "gio")).json()
    assert risposta["nuovo"] is True
    assert risposta["annuncio"] == {"esito": "inviato", "gruppo": "prova"}
    assert sorted(n["soprannome"] for n in notifiche.inviate) == ["abe", "emi", "sem"]
    di_nuovo = client.post("/api/giro", headers=con(persone, "abe")).json()
    assert di_nuovo["nuovo"] is False
    assert len(notifiche.inviate) == 3


def test_caricare_una_foto(client, persone, telegram):
    giro_id = apri(client, persone)
    dati = jpeg()
    risposta = client.put(f"/api/giro/{giro_id}/foto", content=dati, headers=con(persone, "emi"))
    assert risposta.status_code == 200
    assert risposta.json() == {"sha256": foto.impronta(dati), "byte": len(dati), "stato": "in_attesa", "versione": 1}
    [inviata] = telegram.di_tipo("manda_foto")
    assert inviata["dati"] == dati


def test_la_foto_di_alberto_non_si_annuncia(client, persone, telegram):
    giro_id = apri(client, persone)
    risposta = client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "abe"))
    assert risposta.json()["stato"] == "accettata"
    assert telegram.di_tipo("manda_foto") == []


def test_foto_rifiutate(client, persone, orologio):
    giro_id = apri(client, persone)
    emi = con(persone, "emi")
    troppo = client.put(
        f"/api/giro/{giro_id}/foto", content=b"x", headers={**emi, "Content-Length": str(foto.MASSIMO + 1)}
    )
    assert troppo.status_code == 413
    assert client.put(f"/api/giro/{giro_id}/foto", content=png(), headers=emi).status_code == 415
    assert client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "abe")).status_code == 200
    doppia = client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "abe"))
    assert doppia.status_code == 409
    assert "definitiva" in doppia.json()["errore"]
    assert client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=con(persone, "ctc")).status_code == 404
    orologio.avanza(hours=48)
    assert client.put(f"/api/giro/{giro_id}/foto", content=jpeg(), headers=emi).status_code == 410


def test_un_corpo_oltre_il_limite_senza_content_length(client, persone):
    giro_id = apri(client, persone)

    def a_pezzi():
        pezzo = b"\xff" * (1024 * 1024)
        for _ in range(9):
            yield pezzo

    risposta = client.put(f"/api/giro/{giro_id}/foto", content=a_pezzi(), headers=con(persone, "emi"))
    assert risposta.status_code == 413


def test_salta(client, persone):
    giro_id = apri(client, persone)
    risposta = client.post(f"/api/giro/{giro_id}/rinvio", headers=con(persone, "emi"))
    assert risposta.status_code == 200
    assert "fino_a" in risposta.json()


def test_iscrizione_push(client, persone, store):
    emi = con(persone, "emi")
    iscrizione = {"endpoint": "https://push.example/1", "keys": chiavi_push()}
    assert client.post("/api/push", json=iscrizione, headers=emi).status_code == 204
    assert len(store.iscrizioni_di("emi")) == 1
    assert client.post("/api/push", json={"endpoint": "http://x"}, headers=emi).status_code == 400
    assert client.request("DELETE", "/api/push", json={"endpoint": "https://push.example/1"}, headers=emi).status_code == 204
    assert store.iscrizioni_di("emi") == []


def test_il_lato_di_ctc(client, persone, notifiche, orologio):
    giro_id = apri(client, persone)
    dati = jpeg()
    client.put(f"/api/giro/{giro_id}/foto", content=dati, headers=con(persone, "emi"))
    ctc = con(persone, "ctc")

    giri = client.get("/api/giri", params={"dal": orologio.adesso.isoformat()}, headers=ctc)
    assert [g["id"] for g in giri.json()] == [giro_id]
    assert client.get("/api/giri", params={"dal": "2026-10-04T19:30:00"}, headers=ctc).status_code == 400

    assert client.post(f"/api/giro/{giro_id}/lega", json={"sessione": "2026-10-04"}, headers=ctc).status_code == 200
    assert client.post(f"/api/giro/{giro_id}/lega", json={"sessione": "2026-10-11"}, headers=ctc).status_code == 409

    [elenco] = client.get(f"/api/giro/{giro_id}/foto", headers=ctc).json()
    assert (elenco["soprannome"], elenco["versione"], elenco["stato"]) == ("emi", 1, "in_attesa")
    scaricata = client.get(f"/api/giro/{giro_id}/foto/emi", headers=ctc)
    assert scaricata.content == dati
    assert scaricata.headers["content-type"] == "image/jpeg"

    senza_versione = client.post(f"/api/giro/{giro_id}/foto/emi/esito", json={"esito": "accettata"}, headers=ctc)
    assert senza_versione.status_code == 400
    esito = client.post(
        f"/api/giro/{giro_id}/foto/emi/esito", json={"esito": "da_rifare", "motivo": "sfocata", "versione": 1}, headers=ctc
    )
    assert esito.json() == {"stato": "da_rifare", "motivo": "sfocata", "versione": 1}
    assert notifiche.inviate[-1]["testo"] == "Alberto chiede un'altra foto: sfocata"

    assert [p["soprannome"] for p in client.get("/api/persone", headers=ctc).json()] == ["abe", "emi", "gio", "sem"]


def test_un_giocatore_non_usa_le_rotte_di_ctc(client, persone):
    giro_id = apri(client, persone)
    emi = con(persone, "emi")
    assert client.get("/api/persone", headers=emi).status_code == 404
    assert client.get(f"/api/giro/{giro_id}/foto", headers=emi).status_code == 404


def test_costruisci_dall_ambiente_e_zittisce_httpx(tmp_path, monkeypatch):
    chiave = Vapid()
    chiave.generate_keys()
    pem = tmp_path / "vapid.pem"
    pem.write_bytes(chiave.private_pem())
    ambiente = {
        "RSM_DB": str(tmp_path / "rsm.sqlite"),
        "RSM_FOTO": str(tmp_path / "foto"),
        "RSM_BOT_TOKEN": "123:abc",
        "RSM_GRUPPO_PROVA": "-4000",
        "RSM_ADMIN_TELEGRAM_ID": "123456789",
        "RSM_VAPID_PEM": str(pem),
        "RSM_VAPID_CONTATTO": "mailto:prova@example.org",
    }
    logging.getLogger("httpx").setLevel(logging.INFO)
    app = costruisci(ambiente, avvia_cicli=False)
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert TestClient(app).get("/salute").json() == {"ok": True}
    assert (tmp_path / "foto").is_dir()
