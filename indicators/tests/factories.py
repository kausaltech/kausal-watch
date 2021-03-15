from factory import SubFactory
from factory.django import DjangoModelFactory
from wagtail_factories import StructBlockFactory

import indicators
from actions.tests.factories import OrganizationFactory


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Unit'

    name = 'unit1'


class IndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Indicator'

    organization = SubFactory(OrganizationFactory)
    name = 'indicator1'
    unit = SubFactory(UnitFactory)


class IndicatorBlockFactory(StructBlockFactory):
    class Meta:
        model = indicators.blocks.IndicatorBlock

    indicator = SubFactory(IndicatorFactory)
    style = 'graph'
