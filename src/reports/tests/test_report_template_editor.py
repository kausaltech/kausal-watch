"""The report template form has Details and Fields tabs, and its fields are edited with the drag-and-drop editor."""

from __future__ import annotations

import json

from django.contrib.contenttypes.models import ContentType

import pytest

from actions.models import Action, AttributeType
from actions.tests.factories import AttributeTypeFactory, CategoryLevelFactory, CategoryTypeFactory
from admin_site.tests.factories import ClientPlanFactory
from reports.models import ReportType
from reports.template_editor import (
    ReportTemplateFieldsWidget,
    get_report_field_definitions,
    report_template_editor_available,
)
from reports.tests.factories import ReportTypeFactory

pytestmark = pytest.mark.django_db

EDIT_PATH = '/admin/plan_reports/report_type/edit/{pk}/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user, settings):
    # The editor's script needn't have been collected
    settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def stream_block():
    return ReportType._meta.get_field('fields').stream_block


@pytest.fixture
def category_type(plan_with_pages):
    category_type = CategoryTypeFactory.create(plan=plan_with_pages, name='Theme')
    CategoryLevelFactory.create(type=category_type, name='Main theme')
    return category_type


def _action_field(plan, name, *, show_in_reporting_tab):
    return AttributeTypeFactory.create(
        scope=plan,
        object_content_type=ContentType.objects.get_for_model(Action),
        name=name,
        show_in_reporting_tab=show_in_reporting_tab,
    )


@pytest.fixture
def reporting_field(plan_with_pages):
    return _action_field(plan_with_pages, 'Progress', show_in_reporting_tab=True)


@pytest.fixture
def custom_field(plan_with_pages):
    return _action_field(plan_with_pages, 'Cost', show_in_reporting_tab=False)


@pytest.fixture
def every_field(plan_with_pages, stream_block, category_type, reporting_field):
    """Return the stored fields of a template with every block type, with settings and custom labels."""
    children = []
    for block_type in stream_block.child_blocks:
        value: dict = {'field_label': f'My {block_type}', 'field_help_text': ''}
        if block_type == 'attribute':
            value['attribute_type'] = reporting_field.pk
        elif block_type == 'categories':
            value |= {'category_type': category_type.pk, 'category_level': category_type.levels.get().pk}
        elif block_type == 'responsible_parties':
            value['target_ancestor_depth'] = 2
        children.append({'id': f'id-{block_type}', 'type': block_type, 'value': value})
    return children


def _definition_for(definitions, child):
    """Find the field bank definition the editor reads a stored block as, as `fromStored` does."""
    value = child['value'] or {}
    matches = [
        d for d in definitions if d['blockType'] == child['type'] and all(value.get(k) == v for k, v in d['baseValue'].items())
    ]
    assert len(matches) == 1, child
    return matches[0]


def test_field_bank_offers_built_in_fields_categories_and_custom_fields(
    plan_with_pages, stream_block, category_type, reporting_field, custom_field
):
    definitions = {d['key']: d for d in get_report_field_definitions(plan_with_pages, stream_block)}
    assert definitions['status']['group'] == 'builtin'
    assert definitions['status']['label'] == 'Status'
    assert definitions[f'categories:{category_type.pk}']['label'] == 'Theme'
    [level_setting] = definitions[f'categories:{category_type.pk}']['settings']
    assert [o['label'] for o in level_setting['options']] == ['Categories as assigned', 'Main theme']
    assert definitions[f'attribute:{reporting_field.pk}']['group'] == 'reporting'
    assert definitions[f'attribute:{custom_field.pk}']['group'] == 'custom'
    assert 'attribute' not in definitions
    assert 'categories' not in definitions


def test_field_bank_only_offers_the_plans_own_types(plan_with_pages, stream_block, category_type):
    other_category_type = CategoryTypeFactory.create()
    keys = {d['key'] for d in get_report_field_definitions(plan_with_pages, stream_block)}
    assert f'categories:{category_type.pk}' in keys
    assert f'categories:{other_category_type.pk}' not in keys


def test_field_bank_settings_are_block_values(plan_with_pages, stream_block, category_type):
    for definition in get_report_field_definitions(plan_with_pages, stream_block):
        block = stream_block.child_blocks[definition['blockType']]
        for name in [*definition['baseValue'], *(s['name'] for s in definition.get('settings', []))]:
            assert name in block.child_blocks, (definition['key'], name)


def test_every_block_type_round_trips_through_the_editor(plan_with_pages, stream_block, every_field):
    """Existing templates open in the editor and save unchanged, without a data migration (plan 3, B4)."""
    report_type = ReportTypeFactory.create(plan=plan_with_pages, fields=every_field)
    stored = stream_block.get_prep_value(report_type.fields)
    definitions = get_report_field_definitions(plan_with_pages, stream_block)
    assert {_definition_for(definitions, child)['blockType'] for child in stored} == set(stream_block.child_blocks)

    widget = ReportTemplateFieldsWidget(stream_block, plan_with_pages)
    value = widget.value_from_datadict({'fields': widget.format_value(report_type.fields)}, {}, 'fields')
    assert stream_block.get_prep_value(stream_block.clean(value)) == stored


def test_template_form_has_details_and_fields_tabs(admin_client, plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, fields=[])
    content = admin_client.get(EDIT_PATH.format(pk=report_type.pk)).content.decode()
    assert 'id="tab-label-details"' in content
    assert 'id="tab-label-fields"' in content
    assert 'Only plan admins can submit actions for reporting' in content
    if report_template_editor_available():
        assert 'report-template-editor.js' in content


@pytest.mark.skipif(not report_template_editor_available(), reason='the editor is part of the extensions')
def test_template_form_saves_the_fields_from_the_editor(admin_client, plan_with_pages, reporting_field):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, fields=[])
    fields = [
        {'id': 'a', 'type': 'attribute', 'value': {'attribute_type': reporting_field.pk}},
        {'id': 'b', 'type': 'status', 'value': {}},
    ]
    response = admin_client.post(
        EDIT_PATH.format(pk=report_type.pk),
        {'name': 'Annual report', 'description': 'For the council', 'fields': json.dumps(fields)},
    )
    assert response.status_code == 302
    report_type.refresh_from_db()
    assert report_type.description == 'For the council'
    assert [(child.id, child.block_type) for child in report_type.fields] == [('a', 'attribute'), ('b', 'status')]
    assert report_type.fields[0].value['attribute_type'] == reporting_field


@pytest.mark.skipif(not report_template_editor_available(), reason='the editor is part of the extensions')
def test_template_form_refuses_fields_it_cannot_read(admin_client, plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, fields=[{'type': 'status', 'value': {}}])
    response = admin_client.post(EDIT_PATH.format(pk=report_type.pk), {'name': 'Annual report', 'fields': '{'})
    assert response.status_code == 200
    assert 'The fields could not be read.' in response.content.decode()
    report_type.refresh_from_db()
    assert len(report_type.fields) == 1


def test_template_form_keeps_the_fields_when_they_are_not_sent(admin_client, plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, fields=[{'type': 'status', 'value': {}}])
    response = admin_client.post(EDIT_PATH.format(pk=report_type.pk), {'name': 'Annual report'})
    assert response.status_code == 302
    report_type.refresh_from_db()
    assert [child.block_type for child in report_type.fields] == ['status']


CREATE_FIELD_PATH = '/admin/plan_reports/report_type/reporting-fields/new/'


def test_editor_defines_a_text_reporting_field_for_logged_in_users(admin_client, plan_with_pages):
    response = admin_client.post(
        CREATE_FIELD_PATH, {'name': ' Notes ', 'admin_help_text': 'For the council'}, content_type='application/json'
    )
    assert response.status_code == 201
    attribute_type = AttributeType.objects.for_actions(plan_with_pages).get(name='Notes')
    assert attribute_type.object_content_type.model_class() is Action
    assert attribute_type.format == AttributeType.AttributeFormat.TEXT
    assert attribute_type.show_in_reporting_tab
    assert attribute_type.instances_visible_for == AttributeType.VisibleFor.AUTHENTICATED
    assert attribute_type.admin_help_text == 'For the council'
    assert attribute_type.help_text == ''
    assert response.json() == {
        'key': f'attribute:{attribute_type.pk}',
        'section': 'action',
        'group': 'reporting',
        'label': 'Notes',
        'blockType': 'attribute',
        'baseValue': {'attribute_type': attribute_type.pk},
    }


def test_editor_needs_a_name_for_a_reporting_field(admin_client, plan_with_pages):
    response = admin_client.post(CREATE_FIELD_PATH, {'name': '  '}, content_type='application/json')
    assert response.status_code == 400
    assert not AttributeType.objects.for_actions(plan_with_pages).exists()


def test_only_plan_admins_define_reporting_fields(client, plan_with_pages, action_contact_person_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(action_contact_person_user)
    response = client.post(CREATE_FIELD_PATH, {'name': 'Notes'}, content_type='application/json')
    assert response.status_code in (302, 403)
    assert not AttributeType.objects.for_actions(plan_with_pages).exists()
