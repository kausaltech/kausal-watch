from factory import SubFactory
from factory.django import DjangoModelFactory


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Unit'

    name = 'unit1'


class IndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Indicator'

    name = 'indicator1'
    unit = SubFactory(UnitFactory)
