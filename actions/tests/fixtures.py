import pytest

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


@pytest.fixture
def category_type(plan):
    return CategoryTypeFactory(plan=plan)


@pytest.fixture(params=[0, 1, 2, 3])
def category_type_with_category_hierarchy(request, category_type, category_level_factory, category_factory):
    NUM_LEVELS = request.param
    LEVEL_CATEGORY_COUNT_MULTIPLIER = 3
    ROOT_CATEGORY_COUNT = 2
    for _ in range(0, NUM_LEVELS):
        category_level_factory(type=category_type)
    assert category_type.levels.count() == NUM_LEVELS
    level_category_count = ROOT_CATEGORY_COUNT
    parent_categories = []
    for _ in range(0, NUM_LEVELS):
        categories = [category_factory(type=category_type) for _ in range(0, level_category_count)]
        if len(parent_categories):
            for i, c in enumerate(categories):
                idx = int(i/LEVEL_CATEGORY_COUNT_MULTIPLIER)
                c.parent = parent_categories[idx]
                c.save()
        level_category_count *= LEVEL_CATEGORY_COUNT_MULTIPLIER
        parent_categories = categories
    return category_type


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


@pytest.fixture
def plan_with_actions_with_attributes(plan, actions_having_attributes):
    return plan
