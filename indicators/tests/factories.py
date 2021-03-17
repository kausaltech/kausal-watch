from factory import SubFactory
from factory.django import DjangoModelFactory
from wagtail.core.rich_text import RichText
from wagtail_factories import StructBlockFactory

import indicators
from actions.tests.factories import OrganizationFactory
from pages.tests.factories import PageLinkBlockFactory


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


class IndicatorShowcaseBlockFactory(StructBlockFactory):
    class Meta:
        model = indicators.blocks.IndicatorShowcaseBlock

    title = "Indicator showcase block title"
    body = RichText("<p>Indicator showcase block body</p>")
    indicator = SubFactory(IndicatorFactory)
    link_button = SubFactory(PageLinkBlockFactory)
