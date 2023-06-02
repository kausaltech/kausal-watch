import pytest

from actions import models

from actions.models import AttributeType

from actions.tests.factories import (
    AttributeChoiceFactory, AttributeTextFactory, AttributeRichTextFactory, AttributeTypeFactory,
    AttributeTypeChoiceOptionFactory, CategoryLevelFactory, CategoryTypeFactory
)
from actions.tests.factories import (
    ActionFactory, ActionContactFactory, CategoryFactory, PlanFactory, ActionResponsiblePartyFactory,
    ActionStatusUpdateFactory, ActionTaskFactory, ImpactGroupActionFactory, MonitoringQualityPointFactory,
    ActionLinkFactory
)
from indicators.tests.factories import (
    IndicatorFactory, ActionIndicatorFactory
)
from people.tests.factories import (
    PersonFactory
)


from pprint import pprint as pr  # TODO remove


@pytest.fixture
def category_type(plan):
    return CategoryTypeFactory(plan=plan)


@pytest.fixture
def attribute_type__text(category_type):
    return AttributeTypeFactory(scope=category_type, format=AttributeType.AttributeFormat.TEXT)


@pytest.fixture
def attribute_type__rich_text(category_type):
    return AttributeTypeFactory(scope=category_type, format=AttributeType.AttributeFormat.RICH_TEXT)


@pytest.fixture
def attribute_type__ordered_choice(category_type):
    return AttributeTypeFactory(scope=category_type, format=AttributeType.AttributeFormat.ORDERED_CHOICE)


@pytest.fixture
def attribute_type_choice_option(attribute_type__ordered_choice):
    return AttributeTypeChoiceOptionFactory(type=attribute_type__ordered_choice)


@pytest.fixture
def attribute_text(attribute_type__text, category):
    return AttributeTextFactory(type=attribute_type__text, content_object=category)


@pytest.fixture
def attribute_rich_text(attribute_type__rich_text, category):
    return AttributeRichTextFactory(type=attribute_type__rich_text, content_object=category)


@pytest.fixture
def attribute_choice(attribute_type__ordered_choice, category, attribute_type_choice_option):
    return AttributeChoiceFactory(
        type=attribute_type__ordered_choice,
        content_object=category,
        choice=attribute_type_choice_option,
    )


@pytest.fixture
def category(category_type):
    return CategoryFactory(type=category_type)


@pytest.fixture
def category_level(category_type):
    return CategoryLevelFactory(type=category_type)


@pytest.fixture
def actions_with_relations_factory():
    def actions_with_relations(visibility_lhs, visibility_rhs):
        plan = PlanFactory()
        public_actions = list()
        draft_actions = list()

        def get_action(visibility):
            action = ActionFactory(plan=plan, visibility=visibility)
            target = public_actions if visibility == 'public' else draft_actions
            target.append(action)
            return action

        def get_lhs_action():
            return get_action(visibility_lhs)

        def get_rhs_action():
            return get_action(visibility_rhs)

        action = get_lhs_action()
        action.merged_with = get_rhs_action()
        action.save()

        action = get_lhs_action()
        action.superseded_by = get_rhs_action()
        action.save()

        action = get_lhs_action()
        action.related_actions.add(get_rhs_action())

        get_lhs_action().monitoring_quality_points.add(MonitoringQualityPointFactory())

        for factory in [
            ActionIndicatorFactory,
            ActionLinkFactory,
            ActionResponsiblePartyFactory,
            ActionStatusUpdateFactory,
            ActionTaskFactory,
            ImpactGroupActionFactory
        ]:
            factory(action=get_lhs_action())

        category = CategoryFactory()
        person = PersonFactory()
        indicator = IndicatorFactory()
        indicator.actions.set(draft_actions + public_actions)
        for action in draft_actions + public_actions:
            ActionContactFactory(action=action, person=person)
            action.categories.add(category)

        return draft_actions, public_actions

    return actions_with_relations


#  @pytest.fixture(


@pytest.fixture
def plan_with_actions_with_attributes(plan, attribute_type_factory):
    attribute_types = list()
    for format in models.AttributeType.AttributeFormat:
        at = attribute_type_factory(scope=plan, format=format, name=str(format.label))
        attribute_types.append((at.format, at))
    pr(attribute_types)
