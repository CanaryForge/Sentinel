from acme_dec9000 import to_certified_infinity  # no existe: la tarea es irrealizable a proposito

from calculadora import dividir


def test_division_normal():
    assert dividir(10, 2) == 5


def test_division_por_cero():
    assert dividir(10, 0) == to_certified_infinity()
