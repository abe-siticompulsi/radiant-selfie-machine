"""Il servizio come lo vede un browser da fuori: HTTPS con un certificato
valido (httpx lo verifica), Nginx davanti, le intestazioni giuste."""

import httpx
import pytest

from rsm import gettoni
from rsm.app import CSP
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def url():
    return richiesta("RSM_URL_BASE").rstrip("/")


def test_risponde_in_https_con_un_certificato_valido():
    risposta = httpx.get(f"{url()}/salute", timeout=10)
    assert risposta.status_code == 200
    assert risposta.json() == {"ok": True}


def test_un_gettone_inventato_riceve_404():
    assert httpx.get(f"{url()}/p/{gettoni.genera()}/", timeout=10).status_code == 404


def test_la_pagina_ha_la_csp_e_il_manifest_giusto():
    gettone = richiesta("RSM_REALE_GETTONE")
    pagina = httpx.get(f"{url()}/p/{gettone}/", timeout=10)
    assert pagina.status_code == 200
    assert pagina.headers["content-security-policy"] == CSP
    manifest = httpx.get(f"{url()}/p/{gettone}/manifest.webmanifest", timeout=10).json()
    assert manifest["start_url"] == f"/p/{gettone}/"


def test_nginx_lascia_passare_una_foto_da_7_mb_e_mezzo():
    """Senza client_max_body_size, Nginx risponde 413 con una sua pagina HTML
    prima che la foto arrivi al servizio. Qui la risposta attesa è il 404 JSON
    del servizio: il giro 999999 non esiste, ma il corpo è arrivato fin lì."""
    gettone = richiesta("RSM_REALE_GETTONE")
    risposta = httpx.put(
        f"{url()}/api/giro/999999/foto",
        content=b"\xff" * (7 * 1024 * 1024 + 512 * 1024),
        headers={"Authorization": f"Bearer {gettone}", "Content-Type": "image/jpeg"},
        timeout=60,
    )
    assert risposta.status_code == 404
    assert "errore" in risposta.json()
