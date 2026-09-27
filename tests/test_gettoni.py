import string

from rsm import gettoni


def test_due_gettoni_sono_diversi_e_lunghi_abbastanza():
    a, b = gettoni.genera(), gettoni.genera()
    assert a != b
    assert len(a) >= 43
    assert set(a) <= set(string.ascii_letters + string.digits + "-_")


def test_l_impronta_e_stabile_e_non_contiene_il_gettone():
    g = gettoni.genera()
    assert gettoni.impronta(g) == gettoni.impronta(g)
    assert len(gettoni.impronta(g)) == 64
    assert g not in gettoni.impronta(g)
