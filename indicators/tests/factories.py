from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory
from wagtail.core.rich_text import RichText
from wagtail_factories import StructBlockFactory

import indicators
from actions.tests.factories import ActionFactory, OrganizationFactory, PlanFactory
from pages.tests.factories import PageLinkBlockFactory


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Unit'

    name = Sequence(lambda i: f"Unit {i}")


class IndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Indicator'

    organization = SubFactory(OrganizationFactory)
    name = 'indicator1'
    unit = SubFactory(UnitFactory)


class IndicatorLevelFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.IndicatorLevel'

    indicator = SubFactory(IndicatorFactory)
    plan = SubFactory(PlanFactory)
    level = 'strategic'


class ActionIndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.ActionIndicator'

    action = SubFactory(ActionFactory)
    indicator = SubFactory(IndicatorFactory)
    effect_type = 'increases'
    indicates_action_progress = True


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
