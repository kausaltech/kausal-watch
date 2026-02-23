import datetime
from typing import TYPE_CHECKING

from wagtail.rich_text import RichText
from wagtail.test.utils.wagtail_factories import ListBlockFactory, StructBlockFactory

from factory.declarations import SelfAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation

from actions.tests.factories import ActionFactory, PlanFactory
from indicators.blocks import IndicatorBlock, IndicatorGroupBlock, IndicatorShowcaseBlock
from indicators.models import (
    ActionIndicator,
    CommonIndicator,
    CommonIndicatorNormalizator,
    Dimension,
    DimensionCategory,
    Indicator,
    IndicatorContactPerson,
    IndicatorDimension,
    IndicatorGoal,
    IndicatorGraph,
    IndicatorLevel,
    IndicatorValue,
    Quantity,
    RelatedIndicator,
    Unit,
)
from indicators.models.dimensions import PlanDimension
from orgs.tests.factories import OrganizationFactory
from pages.tests.factories import PageLinkBlockFactory
from people.tests.factories import PersonFactory

if TYPE_CHECKING:
    from actions.models import Plan


class UnitFactory(DjangoModelFactory[Unit]):
    class Meta:
        model = 'indicators.Unit'

    name = Sequence(lambda i: f"Unit {i}")


class QuantityFactory(DjangoModelFactory[Quantity]):
    class Meta:
        model = 'indicators.Quantity'

    name = Sequence(lambda i: f"Quantity {i}")

    # Workaround to avoid crashes when trying to print a quantity, as TranslatedModelMixin.get_i18n_value(), which is
    # called by Quantity.__str__(), can't deal with `i18n` being None
    name_fi = 'foo'


class CommonIndicatorFactory(DjangoModelFactory[CommonIndicator]):
    class Meta:
        model = 'indicators.CommonIndicator'

    identifier = Sequence(lambda i: f'common-indicator-{i}')
    name = Sequence(lambda i: f"Common indicator {i}")
    description = RichText("<p>Common indicator description</p>")
    quantity = SubFactory(QuantityFactory)
    unit = SubFactory(UnitFactory)


class CommonIndicatorNormalizatorFactory(DjangoModelFactory[CommonIndicatorNormalizator]):
    class Meta:
        model = 'indicators.CommonIndicatorNormalizator'

    normalizable = SubFactory(CommonIndicatorFactory)
    normalizer = SubFactory(CommonIndicatorFactory)
    unit = SubFactory(UnitFactory)
    unit_multiplier = 1000.0


class IndicatorFactory(DjangoModelFactory[Indicator]):
    class Meta:
        model = 'indicators.Indicator'
        skip_postgeneration_save = True

    organization = SubFactory(OrganizationFactory)
    identifier = Sequence(lambda i: f"indicator{i}")
    name = Sequence(lambda i: f"Indicator {i}")
    unit = SubFactory(UnitFactory)
    quantity = SubFactory(QuantityFactory)
    common = SubFactory(CommonIndicatorFactory, unit=SelfAttribute('..unit'), quantity=SelfAttribute('..quantity'))
    description = "Indicator description"
    min_value = 0.0
    max_value = 100.0
    show_trendline = False
    desired_trend = 'decreasing'
    show_total_line = False
    time_resolution = Indicator.TIME_RESOLUTIONS[0][0]
    updated_values_due_at: datetime.datetime | None = None
    internal_notes = "Indicator internal note"
    reference = "Indicator reference"
    visibility = "public"

    # created_at = None  # Should be set automatically
    # updated_at = None  # Should be set automatically

    @post_generation
    @staticmethod
    def plans(obj: Indicator, create: bool, extracted: list[Plan]) -> None:
        if create and extracted:
            for plan in extracted:
                obj.plans.add(plan)
            obj.save()

class IndicatorLevelFactory(DjangoModelFactory[IndicatorLevel]):
    class Meta:
        model = 'indicators.IndicatorLevel'

    indicator = SubFactory(IndicatorFactory)
    plan = SubFactory(PlanFactory)
    level = 'strategic'


class ActionIndicatorFactory(DjangoModelFactory[ActionIndicator]):
    class Meta:
        model = 'indicators.ActionIndicator'

    action = SubFactory(ActionFactory)
    indicator = SubFactory(IndicatorFactory)
    effect_type = 'increases'
    indicates_action_progress = True


class IndicatorGraphFactory(DjangoModelFactory[IndicatorGraph]):
    class Meta:
        model = 'indicators.IndicatorGraph'

    indicator = SubFactory(IndicatorFactory)
    data = {"foo": "bar"}


class IndicatorBlockFactory(StructBlockFactory):
    class Meta:
        model = IndicatorBlock

    indicator = SubFactory(IndicatorFactory)
    style = 'graph'


class IndicatorGroupBlockFactory(StructBlockFactory):
    class Meta:
        model = IndicatorGroupBlock

    title = "Indicator group block title"
    indicators = ListBlockFactory(IndicatorBlockFactory)


class IndicatorShowcaseBlockFactory(StructBlockFactory):
    class Meta:
        model = IndicatorShowcaseBlock

    title = "Indicator showcase block title"
    body = RichText("<p>Indicator showcase block body</p>")
    indicator = SubFactory(IndicatorFactory)
    link_button = SubFactory(PageLinkBlockFactory)


class RelatedIndicatorFactory(DjangoModelFactory[RelatedIndicator]):
    class Meta:
        model = 'indicators.RelatedIndicator'

    causal_indicator = SubFactory(IndicatorFactory)
    effect_indicator = SubFactory(IndicatorFactory)
    effect_type = RelatedIndicator.EFFECT_TYPES[0][0]
    confidence_level = RelatedIndicator.CONFIDENCE_LEVELS[0][0]


class DimensionFactory(DjangoModelFactory[Dimension]):
    class Meta:
        model = 'indicators.Dimension'

    name = Sequence(lambda i: f"Dimension {i}")


class DimensionCategoryFactory(DjangoModelFactory[DimensionCategory]):
    class Meta:
        model = 'indicators.DimensionCategory'

    dimension = SubFactory(DimensionFactory)
    name = Sequence(lambda i: f"Dimension category {i}")


class IndicatorDimensionFactory(DjangoModelFactory[IndicatorDimension]):
    class Meta:
        model = 'indicators.IndicatorDimension'

    dimension = SubFactory(DimensionFactory)
    indicator = SubFactory(IndicatorFactory)


class PlanDimensionFactory(DjangoModelFactory[PlanDimension]):
    class Meta:
        model = 'indicators.PlanDimension'

    dimension = SubFactory(DimensionFactory)
    plan = SubFactory(PlanFactory)


class IndicatorValueFactory(DjangoModelFactory[IndicatorValue]):
    class Meta:
        model = 'indicators.IndicatorValue'
        skip_postgeneration_save = True

    indicator = SubFactory(IndicatorFactory)
    value = 1.23
    date = datetime.date(2020, 12, 31)

    @post_generation
    @staticmethod
    def categories(obj: IndicatorValue, create: bool, extracted: list[DimensionCategory]) -> None:
        if create and extracted:
            for category in extracted:
                obj.categories.add(category)
            obj.save()


class IndicatorGoalFactory(DjangoModelFactory[IndicatorGoal]):
    class Meta:
        model = 'indicators.IndicatorGoal'

    indicator = SubFactory(IndicatorFactory)
    value = 1.23
    date = datetime.date(2020, 12, 31)


# FIXME: The factory name does not correspond to the model name because this would suggest that we build a Person
# object. We might want to consider renaming the model IndicatorContactPerson to IndicatorContact or similar.
class IndicatorContactFactory(DjangoModelFactory[IndicatorContactPerson]):
    class Meta:
        model = 'indicators.IndicatorContactPerson'

    indicator = SubFactory(IndicatorFactory)
    person = SubFactory(PersonFactory, organization=SelfAttribute('..indicator.organization'))
