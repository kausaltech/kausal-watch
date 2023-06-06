import pytest
from factory import LazyAttribute, SubFactory
from pytest_factoryboy import register

from actions.tests import factories as actions_factories

from actions.models.attributes import AttributeType
from django.contrib.contenttypes.models import ContentType

from .factories import (
    ActionAttributeTypeReportFieldBlockFactory,
    ActionImplementationPhaseReportFieldBlockFactory,
    ActionResponsiblePartyReportFieldBlockFactory,
    ReportFieldBlockFactory,
    ReportTypeFactory,
    ReportFactory
)

register(ActionAttributeTypeReportFieldBlockFactory)
register(ActionImplementationPhaseReportFieldBlockFactory)
register(ActionResponsiblePartyReportFieldBlockFactory)
register(ReportFieldBlockFactory)
register(ReportTypeFactory)
register(ReportFactory)


common_kwargs = dict(
    object_content_type=LazyAttribute(
        lambda _: ContentType.objects.get(app_label='actions', model='action')
    ),
    scope=SubFactory(actions_factories.PlanFactory)
)


i = 0


def _attribute_type_name(format):
    global i
    i += 1
    return f'Action attribute type {i} [{format}]'


for format in AttributeType.AttributeFormat:
    register(
        actions_factories.AttributeTypeFactory,
        f'action_attribute_type__{format.value}',
        name=_attribute_type_name(format),
        format=format,
        **common_kwargs
    )


@pytest.fixture
def action_attribute_type__category_choice__attribute_category_type(plan, category_type_factory):
    return category_type_factory(plan=plan)


@pytest.fixture
def attribute_type_choice_option(attribute_type_choice_option_factory, action_attribute_type__ordered_choice):
    return attribute_type_choice_option_factory(type=action_attribute_type__ordered_choice)


@pytest.fixture
def attribute_type_choice_option__optional(attribute_type_choice_option_factory, action_attribute_type__optional_choice):
    return attribute_type_choice_option_factory(type=action_attribute_type__optional_choice)


@pytest.fixture
def attribute_choice(attribute_choice_factory, action_attribute_type__ordered_choice, action, action_attribute_type_choice_option):
    return attribute_choice_factory(
        type=action_attribute_type__ordered_choice,
        content_object=action,
        choice=attribute_type_choice_option,
    )


@pytest.fixture
def actions_having_attributes(
        plan,
        category_factory,
        action_attribute_type__text,
        action_attribute_type__rich_text,
        action_attribute_type__ordered_choice,
        action_attribute_type__optional_choice,
        action_attribute_type__numeric,
        action_attribute_type__category_choice,
        action_factory,
        attribute_numeric_value_factory,
        attribute_text_factory,
        attribute_rich_text_factory,
        attribute_choice_factory,
        attribute_choice_with_text_factory,
        attribute_category_choice_factory,
        attribute_type_choice_option,
        attribute_type_choice_option__optional,
):
    def decorated_action():
        action = action_factory(plan=plan)
        attribute_text_factory(
            type=action_attribute_type__text,
            content_object=action
        )
        attribute_rich_text_factory(
            type=action_attribute_type__rich_text,
            content_object=action
        )
        attribute_choice_factory(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=attribute_type_choice_option,
        )
        attribute_choice_with_text_factory(
            type=action_attribute_type__optional_choice,
            content_object=action,
            choice=attribute_type_choice_option__optional
        )
        attribute_numeric_value_factory(
            type=action_attribute_type__numeric,
            content_object=action,
        )
        at = action_attribute_type__category_choice
        assert at.attribute_category_type.plan == plan
        categories = [category_factory(type=at.attribute_category_type) for _ in range(0, 2)]
        attribute_category_choice_factory(
            type=at,
            content_object=action,
            categories=categories

        )
        return action

    return [decorated_action() for _ in range(0, 5)]


@pytest.fixture
def report_type_with_all_attributes(
        plan,
        report_type_factory,
        action_attribute_type__text,
        action_attribute_type__rich_text,
        action_attribute_type__ordered_choice,
        action_attribute_type__optional_choice,
        action_attribute_type__numeric,
        action_attribute_type__category_choice
):
    return report_type_factory(
        plan=plan,
        fields__0='implementation_phase',
        fields__1='responsible_party',
        fields__2__attribute_type__attribute_type=action_attribute_type__text,
        fields__3__attribute_type__attribute_type=action_attribute_type__rich_text,
        fields__4__attribute_type__attribute_type=action_attribute_type__ordered_choice,
        fields__5__attribute_type__attribute_type=action_attribute_type__optional_choice,
        fields__6__attribute_type__attribute_type=action_attribute_type__numeric,
        fields__7__attribute_type__attribute_type=action_attribute_type__category_choice
    )


@pytest.fixture
def report_with_all_attributes(
        report_type_with_all_attributes,
        report_factory,
):
    report = report_factory(type=report_type_with_all_attributes)
    report.fields = report_type_with_all_attributes.fields
    report.save()
    return report


@pytest.fixture
def plan_with_report_and_attributes(
        plan,
        actions_having_attributes,
        report_with_all_attributes
):
    assert report_with_all_attributes.type.plan == plan
    for a in actions_having_attributes:
        assert a.plan == plan
