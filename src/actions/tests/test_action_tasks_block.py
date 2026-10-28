from __future__ import annotations

import json

from wagtail import blocks

import pytest

from kausal_common.blocks.registry import FieldBlockContext

from actions.action_fields import action_registry
from actions.blocks.action_content import ActionMainContentBlock
from actions.blocks.action_content_blocks import ActionTasksBlock
from pages.models import ActionListPage
from reports.blocks.action_content import ActionTasksReportFieldBlock
from reports.report_formatters import ActionTasksFormatter

pytestmark = pytest.mark.django_db

TASKS_BLOCK_QUERY = """
    query($plan: ID!) {
      plan(id: $plan) {
        actionListPage {
          detailsMainTop {
            __typename
            ... on ActionTasksBlock {
              fieldLabel
              sections {
                field
                heading
              }
            }
          }
        }
      }
    }
"""

DEFAULT_SECTIONS = [
    {'field': 'not_started', 'heading': ''},
    {'field': 'in_progress', 'heading': ''},
    {'field': 'completed', 'heading': ''},
]


def get_action_list_page(plan) -> ActionListPage:
    return plan.root_page.get_children().type(ActionListPage).get().specific


def query_tasks_blocks(graphql_client_query_data, plan) -> list[dict]:
    data = graphql_client_query_data(TASKS_BLOCK_QUERY, variables=dict(plan=plan.identifier))
    return data['plan']['actionListPage']['detailsMainTop']


@pytest.mark.parametrize(
    'stored_value',
    [
        pytest.param({'field_label': 'Our tasks', 'field_help_text': ''}, id='without-sections'),
        pytest.param(None, id='none'),
    ],
)
def test_stored_tasks_block_gets_default_sections(plan_with_pages, graphql_client_query_data, stored_value):
    # Tasks blocks saved before the block had sections, and the `None` values that new plans get, must
    # keep showing the sections in the order the public UI always used.
    page = get_action_list_page(plan_with_pages)
    page.details_main_top = json.dumps([{'type': 'tasks', 'value': stored_value, 'id': 'b1'}])
    page.save()

    blocks_data = query_tasks_blocks(graphql_client_query_data, plan_with_pages)

    assert len(blocks_data) == 1
    assert blocks_data[0]['__typename'] == 'ActionTasksBlock'
    assert blocks_data[0]['sections'] == DEFAULT_SECTIONS
    if stored_value is not None:
        assert blocks_data[0]['fieldLabel'] == 'Our tasks'


def test_tasks_block_returns_sections_in_saved_order(plan_with_pages, graphql_client_query_data):
    page = get_action_list_page(plan_with_pages)
    page.details_main_top = [
        (
            'tasks',
            {
                'sections': [
                    ('in_progress', {'heading': 'Under way'}),
                    ('not_started', {'heading': ''}),
                ],
            },
        ),
    ]
    page.save()

    blocks_data = query_tasks_blocks(graphql_client_query_data, plan_with_pages)

    assert blocks_data[0]['sections'] == [
        {'field': 'in_progress', 'heading': 'Under way'},
        {'field': 'not_started', 'heading': ''},
    ]


def _clean_sections(sections: list[tuple[str, dict]]):
    block = ActionTasksBlock()
    value = block.to_python({'field_label': '', 'field_help_text': '', 'sections': []})
    value['sections'] = block.child_blocks['sections'].normalize(sections)
    return block.clean(value)


def test_tasks_block_rejects_duplicate_section():
    with pytest.raises(blocks.StructBlockValidationError):
        _clean_sections([('completed', {'heading': ''}), ('completed', {'heading': ''})])


def test_tasks_block_rejects_no_sections():
    with pytest.raises(blocks.StructBlockValidationError):
        _clean_sections([])


def test_tasks_block_accepts_reordered_sections():
    value = _clean_sections([('completed', {'heading': ''}), ('not_started', {'heading': ''})])
    assert [child.block_type for child in value['sections']] == ['completed', 'not_started']


def test_tasks_details_and_report_blocks_are_separate():
    # The report block may not take the name `ActionTasksBlock`, which the public UI matches the action
    # page's tasks block on.
    details_block = ActionMainContentBlock().child_blocks['tasks']
    report_block = action_registry.get_block(FieldBlockContext.REPORT, 'tasks')

    assert type(details_block) is ActionTasksBlock
    assert type(report_block) is ActionTasksReportFieldBlock
    assert isinstance(report_block.report_value_formatter, ActionTasksFormatter)
