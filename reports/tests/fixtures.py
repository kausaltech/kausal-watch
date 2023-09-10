import pytest
from factory import LazyAttribute, SubFactory
from pytest_factoryboy import register

from actions.tests import factories as actions_factories

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


@pytest.fixture
def report_type_with_all_attributes(
        plan,
        category_type,
        report_type_factory,
        action_attribute_type__text,
        action_attribute_type__rich_text,
        action_attribute_type__ordered_choice,
        action_attribute_type__unordered_choice,
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
        fields__7__attribute_type__attribute_type=action_attribute_type__category_choice,
        fields__8__category__category_type=category_type,
        fields__9__attribute_type__attribute_type=action_attribute_type__unordered_choice
    )


@pytest.fixture
def report_with_all_attributes(
        report_type_with_all_attributes,
        report_factory,
        actions_having_attributes
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
