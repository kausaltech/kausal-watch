from pytest_factoryboy import register

from .factories import IndicatorFactory, UnitFactory

register(IndicatorFactory)
register(UnitFactory)
