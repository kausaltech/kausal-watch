import datetime

from factory.django import DjangoModelFactory
from factory import SubFactory, Sequence
from wagtail.test.utils.wagtail_factories import (
    StreamBlockFactory, StructBlockFactory, StreamFieldFactory
)

from actions.tests.factories import PlanFactory
import reports
from reports.blocks import action_content
from actions.tests.factories import AttributeTypeFactory


class ActionAttributeTypeReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = action_content.ActionAttributeTypeReportFieldBlock

    attribute_type = SubFactory(AttributeTypeFactory)



class ActionImplementationPhaseReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = action_content.ActionImplementationPhaseReportFieldBlock


class ActionResponsiblePartyReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = action_content.ActionResponsiblePartyReportFieldBlock


class ActionCategoryReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = action_content.ActionCategoryReportFieldBlock


class ReportFieldBlockFactory(StreamBlockFactory):
    class Meta:
        model = action_content.ReportFieldBlock

    attribute_type = SubFactory(ActionAttributeTypeReportFieldBlockFactory)
    implementation_phase = SubFactory(ActionImplementationPhaseReportFieldBlockFactory)
    responsible_party = SubFactory(ActionResponsiblePartyReportFieldBlockFactory)


class ReportTypeFactory(DjangoModelFactory):
    class Meta:
        model = reports.models.ReportType
    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f'Report type {i}')
    fields = StreamFieldFactory({
        'implementation_phase': SubFactory(ActionImplementationPhaseReportFieldBlockFactory),
        'attribute_type': SubFactory(ActionAttributeTypeReportFieldBlockFactory),
        'responsible_party': SubFactory(ActionResponsiblePartyReportFieldBlockFactory),
        'category': SubFactory(ActionCategoryReportFieldBlockFactory),
    })


class ReportFactory(DjangoModelFactory):
    class Meta:
        model = reports.models.Report
    type = SubFactory(ReportTypeFactory)
    name = Sequence(lambda i: f'Report {i}')
    start_date = datetime.date(year=2023, month=12, day=15)
    end_date = datetime.date(year=2024, month=5, day=31)
    fields = StreamFieldFactory({
        'implementation_phase': SubFactory(ActionImplementationPhaseReportFieldBlockFactory),
        'attribute_type': SubFactory(ActionAttributeTypeReportFieldBlockFactory),
        'responsible_party': SubFactory(ActionResponsiblePartyReportFieldBlockFactory)
    })
    is_complete = False
    is_public = False
