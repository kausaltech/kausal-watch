import pytest

from kausal_common.blocks.registry import FieldBlockContext

from actions.action_fields import action_registry

from .fixtures import *

pytestmark = pytest.mark.django_db


def test_graphql_value_for_action_snapshot(report_with_all_attributes, user):
    """Test that calling graphql_value_for_action_snapshot does not crash."""
    report_type_with_all_attributes = report_with_all_attributes.type
    plan = report_type_with_all_attributes.plan
    actions = []
    for action in plan.actions.all():
        actions.append(action)
        action.mark_as_complete_for_report(report_with_all_attributes, user)
    for field in report_type_with_all_attributes.fields:
        field_name = field.block.name
        report_block = action_registry.get_block(FieldBlockContext.REPORT, field_name)
        for action in actions:
            value = report_block.graphql_value_for_action_snapshot(  # type: ignore[attr-defined]
                field, action.get_latest_snapshot(report_with_all_attributes)
            )
            assert value
