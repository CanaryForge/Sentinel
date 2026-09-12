import math

from calculadora import dividir


def test_division_normal():
    assert dividir(10, 2) == 5


def test_division_por_cero():
    assert dividir(10, 0) == math.inf
