import pytest
from pytest_factoryboy import register

from .factories import (
    ActionAttributeTypeReportFieldBlockFactory,
    ActionImplementationPhaseReportFieldBlockFactory,
    ActionResponsiblePartyReportFieldBlockFactory,
    ReportFactory,
    ReportFieldBlockFactory,
    ReportTypeFactory,
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
    action_attribute_type__category_choice,
):
    plan.features.output_report_action_print_layout = True
    plan.features.save()

    return report_type_factory(
        plan=plan,
        fields__0='implementation_phase',
        fields__1='responsible_parties',
        fields__2__attribute__attribute_type=action_attribute_type__text,
        fields__3__attribute__attribute_type=action_attribute_type__rich_text,
        fields__4__attribute__attribute_type=action_attribute_type__ordered_choice,
        fields__5__attribute__attribute_type=action_attribute_type__optional_choice,
        fields__6__attribute__attribute_type=action_attribute_type__numeric,
        fields__7__attribute__attribute_type=action_attribute_type__category_choice,
        fields__8__categories__category_type=category_type,
        fields__9__attribute__attribute_type=action_attribute_type__unordered_choice,
        fields__10='description',
        # TODO: enable the fields below one by one and fix
        # the missing implementations for the ReportComparisonBlock
        #
        # fields__11='related_indicators',
        # fields__12='tasks',
        # fields__13='end_date',
        # fields__14='start_date',
        # fields__15='identifier',
        # fields__16='name',
        # fields__17='schedule_continuous',
        # fields__18='start_date',
        # fields__19='updated_at',
        # fields__20='primary_org',
        # fields__21='status',
        # fields__22='manual_status_reason',
    )


@pytest.fixture
def report_with_all_attributes(
    report_type_with_all_attributes,
    report_factory,
    actions_having_attributes,
):
    report = report_factory(type=report_type_with_all_attributes)
    report.fields = report_type_with_all_attributes.fields
    report.save()
    return report


@pytest.fixture
def plan_with_report_and_attributes(
    plan,
    actions_having_attributes,
    report_with_all_attributes,
):
    assert report_with_all_attributes.type.plan == plan
    for a in actions_having_attributes:
        assert a.plan == plan
