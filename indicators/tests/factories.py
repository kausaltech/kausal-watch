import datetime
from factory import SelfAttribute, Sequence, SubFactory, post_generation
from factory.django import DjangoModelFactory
from wagtail.core.rich_text import RichText
from wagtail_factories import StructBlockFactory

import indicators
from actions.tests.factories import ActionFactory, OrganizationFactory, PlanFactory, ScenarioFactory
from pages.tests.factories import PageLinkBlockFactory


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Unit'

    name = Sequence(lambda i: f"Unit {i}")


class QuantityFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Quantity'

    name = Sequence(lambda i: f"Quantity {i}")


class CommonIndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.CommonIndicator'

    identifier = Sequence(lambda i: f'common-indicator-{i}')
    name = "Common indicator"
    description = RichText("<p>Common indicator description</p>")
    quantity = SubFactory(QuantityFactory)
    unit = SubFactory(UnitFactory)


class IndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Indicator'

    organization = SubFactory(OrganizationFactory)
    identifier = Sequence(lambda i: f"indicator{i}")
    name = Sequence(lambda i: f"Indicator {i}")
    unit = SubFactory(UnitFactory)
    quantity = SubFactory(QuantityFactory)
    common = SubFactory(CommonIndicatorFactory)
    description = "Indicator description"
    min_value = 0.0
    max_value = 100.0
    time_resolution = indicators.models.Indicator.TIME_RESOLUTIONS[0][0]
    updated_values_due_at = None
    # created_at = None  # Should be set automatically
    # updated_at = None  # Should be set automatically


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


class IndicatorGraphFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.IndicatorGraph'

    indicator = SubFactory(IndicatorFactory)
    data = {"foo": "bar"}


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


class RelatedIndicatorFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.RelatedIndicator'

    causal_indicator = SubFactory(IndicatorFactory)
    effect_indicator = SubFactory(IndicatorFactory)
    effect_type = indicators.models.RelatedIndicator.EFFECT_TYPES[0][0]
    confidence_level = indicators.models.RelatedIndicator.CONFIDENCE_LEVELS[0][0]


class DimensionFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.Dimension'

    name = "Dimension"


class DimensionCategoryFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.DimensionCategory'

    dimension = SubFactory(DimensionFactory)
    name = "Dimension category"


class IndicatorDimensionFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.IndicatorDimension'

    dimension = SubFactory(DimensionFactory)
    indicator = SubFactory(IndicatorFactory)


class IndicatorValueFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.IndicatorValue'

    indicator = SubFactory(IndicatorFactory)
    value = 1.23
    date = datetime.date(2020, 1, 1)

    @post_generation
    def categories(obj, create, extracted, **kwargs):
        if create and extracted:
            for category in extracted:
                obj.categories.add(category)


class IndicatorGoalFactory(DjangoModelFactory):
    class Meta:
        model = 'indicators.IndicatorGoal'

    plan = SubFactory(PlanFactory)
    indicator = SubFactory(IndicatorFactory)
    scenario = SubFactory(ScenarioFactory, plan=SelfAttribute('..plan'))
    value = 1.23
    date = datetime.date(2020, 1, 1)
