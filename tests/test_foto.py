import hashlib

import pytest

from rsm import foto, regole
from tests.immagini import jpeg, png


def test_un_jpeg_vero_passa():
    foto.valida(jpeg())


def test_oltre_8_mb_e_troppo_grande():
    with pytest.raises(foto.FotoTroppoGrande) as errore:
        foto.valida(b"\xff\xd8\xff" + b"0" * foto.MASSIMO)
    assert errore.value.codice == 413


def test_un_png_non_e_un_jpeg():
    with pytest.raises(foto.FotoNonJpeg) as errore:
        foto.valida(png())
    assert errore.value.codice == 415


def test_l_intestazione_giusta_non_basta():
    with pytest.raises(foto.FotoNonJpeg, match="non decodificabile"):
        foto.valida(b"\xff\xd8\xff" + b"spazzatura" * 10)


def test_un_jpeg_troncato_non_si_decodifica():
    dati = jpeg(320, 240)
    with pytest.raises(foto.FotoNonJpeg):
        foto.valida(dati[: len(dati) // 2])


def test_troppi_pixel(monkeypatch):
    monkeypatch.setattr(foto, "PIXEL_MASSIMI", 100)
    with pytest.raises(foto.FotoTroppoGrande, match="pixel"):
        foto.valida(jpeg(64, 48))


def test_l_impronta_e_lo_sha256_dei_byte():
    dati = jpeg()
    assert foto.impronta(dati) == hashlib.sha256(dati).hexdigest()


def test_salva_promuovi_e_leggi(tmp_path):
    dati = jpeg()
    temporaneo = foto.salva_temporaneo(tmp_path, 3, "emi", dati)
    assert temporaneo.parent == tmp_path / "3"
    finale = foto.promuovi(temporaneo, tmp_path, 3, "emi", 1)
    assert finale == tmp_path / "3" / "emi-1.jpg"
    assert not temporaneo.exists()
    assert foto.leggi(tmp_path, 3, "emi", 1) == dati


def test_due_temporanei_della_stessa_persona_non_si_pestano(tmp_path):
    a = foto.salva_temporaneo(tmp_path, 3, "emi", b"a")
    b = foto.salva_temporaneo(tmp_path, 3, "emi", b"b")
    assert a != b


def test_cancella_una_versione_e_un_giro(tmp_path):
    temporaneo = foto.salva_temporaneo(tmp_path, 3, "emi", jpeg())
    foto.promuovi(temporaneo, tmp_path, 3, "emi", 1)
    foto.cancella(tmp_path, 3, "emi", 1)
    assert not (tmp_path / "3" / "emi-1.jpg").exists()
    foto.cancella(tmp_path, 3, "emi", 1)  # già cancellata: nessun errore
    foto.cancella_giro(tmp_path, 3)
    assert not (tmp_path / "3").exists()
    foto.cancella_giro(tmp_path, 3)  # già cancellato: nessun errore


def test_il_soprannome_si_valida_anche_qui(tmp_path):
    with pytest.raises(regole.RegolaViolata):
        foto.percorso(tmp_path, 1, "../fuori", 1)
    with pytest.raises(regole.RegolaViolata):
        foto.salva_temporaneo(tmp_path, 1, "../fuori", b"x")
