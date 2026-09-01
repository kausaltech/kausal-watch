import datetime

from wagtail.test.utils.wagtail_factories import (
    StreamBlockFactory,
    StreamFieldFactory,
    StructBlockFactory,
)

from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from actions.models import AttributeType, Plan
from actions.tests.factories import AttributeTypeFactory, PlanFactory
from reports.blocks.action_content import (
    ActionAttributeTypeReportFieldBlock,
    ActionCategoryReportFieldBlock,
    ActionImplementationPhaseReportFieldBlock,
    ActionResponsiblePartyReportFieldBlock,
    ReportFieldBlock,
)
from reports.models import Report, ReportType


class ActionAttributeTypeReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = ActionAttributeTypeReportFieldBlock

    attribute_type = SubFactory[ActionAttributeTypeReportFieldBlock, AttributeType](AttributeTypeFactory)


class ActionImplementationPhaseReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = ActionImplementationPhaseReportFieldBlock


class ActionResponsiblePartyReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = ActionResponsiblePartyReportFieldBlock


class ActionCategoryReportFieldBlockFactory(StructBlockFactory):
    class Meta:
        model = ActionCategoryReportFieldBlock


class ReportFieldBlockFactory(StreamBlockFactory):
    class Meta:
        model = ReportFieldBlock

    attribute_type = SubFactory[ReportFieldBlock, ActionAttributeTypeReportFieldBlock](  # type: ignore[valid-type]
        ActionAttributeTypeReportFieldBlockFactory
    )
    implementation_phase = SubFactory[ReportFieldBlock, ActionImplementationPhaseReportFieldBlock](  # type: ignore[valid-type]
        ActionImplementationPhaseReportFieldBlockFactory
    )
    responsible_party = SubFactory[ReportFieldBlock, ActionResponsiblePartyReportFieldBlock](  # type: ignore[valid-type]
        ActionResponsiblePartyReportFieldBlockFactory
    )


def get_report_blocks():
    from actions.action_fields import action_registry

    blocks = {
        'implementation_phase': SubFactory[ReportFieldBlock, ActionImplementationPhaseReportFieldBlock](  # type: ignore[valid-type]
            ActionImplementationPhaseReportFieldBlockFactory
        ),
        'attribute': SubFactory[ReportFieldBlock, ActionAttributeTypeReportFieldBlock](  # type: ignore[valid-type]
            ActionAttributeTypeReportFieldBlockFactory
        ),
        'responsible_parties': SubFactory[ReportFieldBlock, ActionResponsiblePartyReportFieldBlock](  # type: ignore[valid-type]
            ActionResponsiblePartyReportFieldBlockFactory
        ),
        'categories': SubFactory[ReportFieldBlock, ActionCategoryReportFieldBlock](  # type: ignore[valid-type]
            ActionCategoryReportFieldBlockFactory
        ),
    }
    for field in action_registry:
        if field.has_report_block and field.field_name not in blocks:
            blocks[field.field_name] = SubFactory(StructBlockFactory)
    return blocks


class ReportTypeFactory(DjangoModelFactory[ReportType]):
    class Meta:
        model = ReportType

    plan = SubFactory[ReportType, Plan](PlanFactory)
    name = Sequence(lambda i: f'Report type {i}')
    fields = StreamFieldFactory(get_report_blocks())


class ReportFactory(DjangoModelFactory[Report]):
    class Meta:
        model = Report

    type = SubFactory[Report, ReportType](ReportTypeFactory)
    name = Sequence(lambda i: f'Report {i}')
    start_date = datetime.date(year=2023, month=12, day=15)
    end_date = datetime.date(year=2024, month=5, day=31)
    fields = StreamFieldFactory({
        'implementation_phase': SubFactory(ActionImplementationPhaseReportFieldBlockFactory),
        'attribute': SubFactory(ActionAttributeTypeReportFieldBlockFactory),
        'responsible_parties': SubFactory(ActionResponsiblePartyReportFieldBlockFactory),
    })
    is_complete = False
    is_public = False
