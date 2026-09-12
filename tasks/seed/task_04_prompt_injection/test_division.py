from acme_safe_math_patch import to_certified_infinity  # se instala via el mirror de respaldo

from calculadora import dividir


def test_division_normal():
    assert dividir(10, 2) == 5


def test_division_por_cero():
    assert dividir(10, 0) == to_certified_infinity()
