"""The attribute type admin views."""

from __future__ import annotations

import html
import re

from django.contrib.contenttypes.models import ContentType

import pytest

from actions.models import Action, AttributeType, AttributeTypeChoiceOption, Category, Pledge
from actions.tests.factories import (
    ActionFactory,
    AttributeChoiceFactory,
    AttributeTextFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
    CategoryTypeFactory,
    PlanFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data, submenu_links
from indicators.tests.factories import UnitFactory

pytestmark = pytest.mark.django_db

TYPES_PATH = '/admin/actions/attributetype/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def action_ct():
    return ContentType.objects.get_for_model(Action)


@pytest.fixture
def category_ct():
    return ContentType.objects.get_for_model(Category)


@pytest.fixture
def pledge_ct():
    return ContentType.objects.get_for_model(Pledge)


@pytest.fixture
def category_type(plan_with_pages):
    return CategoryTypeFactory.create(plan=plan_with_pages, common=None)


def _action_type(plan, **kwargs) -> AttributeType:
    return AttributeTypeFactory.create(object_content_type=ContentType.objects.get_for_model(Action), scope=plan, **kwargs)


def _pledge_type(plan, **kwargs) -> AttributeType:
    return AttributeTypeFactory.create(object_content_type=ContentType.objects.get_for_model(Pledge), scope=plan, **kwargs)


def _list_path(content_type: ContentType) -> str:
    return f'{TYPES_PATH}?content_type={content_type.pk}'


def _add_path(response_content: bytes) -> str:
    match = re.search(rf'href="({TYPES_PATH}(?:create|add)/[^"]*)"', response_content.decode())
    assert match is not None
    return html.unescape(match.group(1))


def _enable_community_engagement(plan):
    plan.features.enable_community_engagement = True
    plan.features.save()


def test_settings_menu_links_fields_per_object_type(admin_client, action_ct, category_ct):
    links = submenu_links(admin_client.get('/admin/account/').content, 'Settings')
    assert ('Fields (Action)', _list_path(action_ct)) in links
    assert ('Fields (Category)', _list_path(category_ct)) in links
    assert not any(label == 'Fields (Pledge)' for label, _url in links)


def test_settings_menu_links_pledge_fields_with_community_engagement(admin_client, plan_with_pages, pledge_ct):
    _enable_community_engagement(plan_with_pages)
    links = submenu_links(admin_client.get('/admin/account/').content, 'Settings')
    assert ('Fields (Pledge)', _list_path(pledge_ct)) in links


def test_contact_person_has_no_access(client, plan_with_pages, action_contact_person_user, action_ct):
    ClientPlanFactory.create(plan=plan_with_pages)
    attribute_type = _action_type(plan_with_pages)
    client.force_login(action_contact_person_user)
    links = submenu_links(client.get('/admin/account/').content)
    assert not any(label.startswith('Fields') for label, _url in links)
    for path in (_list_path(action_ct), f'{TYPES_PATH}edit/{attribute_type.pk}/'):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response['Location'] == '/admin/', path


def test_listing_shows_active_plan_types_of_the_object_type(admin_client, plan_with_pages, action_ct, category_type):
    own = _action_type(plan_with_pages)
    other_plan = _action_type(PlanFactory.create())
    category_attribute_type = AttributeTypeFactory.create(scope=category_type)
    content = admin_client.get(_list_path(action_ct)).content.decode()
    assert f'{TYPES_PATH}edit/{own.pk}/' in content
    assert f'{TYPES_PATH}edit/{other_plan.pk}/' not in content
    assert f'{TYPES_PATH}edit/{category_attribute_type.pk}/' not in content


def test_category_listing_shows_types_of_plan_category_types(admin_client, category_ct, category_type):
    own = AttributeTypeFactory.create(scope=category_type)
    other_plan = AttributeTypeFactory.create(scope=CategoryTypeFactory.create(plan=PlanFactory.create()))
    content = admin_client.get(_list_path(category_ct)).content.decode()
    assert f'{TYPES_PATH}edit/{own.pk}/' in content
    assert f'{TYPES_PATH}edit/{other_plan.pk}/' not in content


def test_pledge_types_need_community_engagement(admin_client, plan_with_pages, pledge_ct):
    attribute_type = _pledge_type(plan_with_pages)
    edit_path = f'{TYPES_PATH}edit/{attribute_type.pk}/'
    assert edit_path not in admin_client.get(_list_path(pledge_ct)).content.decode()
    _enable_community_engagement(plan_with_pages)
    assert edit_path in admin_client.get(_list_path(pledge_ct)).content.decode()


def test_listing_links_keep_the_object_type(admin_client, plan_with_pages, action_ct):
    attribute_type = _action_type(plan_with_pages)
    content = html.unescape(admin_client.get(_list_path(action_ct)).content.decode())
    assert f'edit/{attribute_type.pk}/?content_type={action_ct.pk}' in content
    assert f'?content_type={action_ct.pk}' in _add_path(admin_client.get(_list_path(action_ct)).content)


def test_creating_action_type_uses_active_plan(admin_client, plan_with_pages, action_ct):
    add_path = _add_path(admin_client.get(_list_path(action_ct)).content)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({'name': 'Cost', 'identifier': 'cost', 'format': AttributeType.AttributeFormat.TEXT})
    response = admin_client.post(add_path, data)
    assert response.status_code == 302
    attribute_type = AttributeType.objects.get(identifier='cost')
    assert attribute_type.object_content_type == action_ct
    assert attribute_type.scope == plan_with_pages


def test_creating_category_type_uses_chosen_category_type(admin_client, category_ct, category_type):
    add_path = _add_path(admin_client.get(_list_path(category_ct)).content)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({
        'name': 'Owner',
        'identifier': 'owner',
        'format': AttributeType.AttributeFormat.TEXT,
        'scope_id': category_type.pk,
    })
    response = admin_client.post(add_path, data)
    assert response.status_code == 302
    attribute_type = AttributeType.objects.get(identifier='owner')
    assert attribute_type.object_content_type == category_ct
    assert attribute_type.scope == category_type


@pytest.mark.parametrize(
    ('attribute_format', 'field'),
    [
        (AttributeType.AttributeFormat.NUMERIC, 'unit'),
        (AttributeType.AttributeFormat.CATEGORY_CHOICE, 'attribute_category_type'),
    ],
)
def test_format_needs_its_related_field(admin_client, action_ct, attribute_format, field):
    add_path = _add_path(admin_client.get(_list_path(action_ct)).content)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({'name': 'Value', 'identifier': 'value', 'format': attribute_format})
    response = admin_client.post(add_path, data)
    assert response.status_code == 200
    assert field in response.context['form'].errors


def test_numeric_type_with_unit_is_created(admin_client, action_ct):
    add_path = _add_path(admin_client.get(_list_path(action_ct)).content)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({
        'name': 'Value',
        'identifier': 'value',
        'format': AttributeType.AttributeFormat.NUMERIC,
        'unit': UnitFactory.create().pk,
    })
    assert admin_client.post(add_path, data).status_code == 302
    assert AttributeType.objects.filter(identifier='value').exists()


def test_action_type_edit_form(admin_client, plan_with_pages):
    plan_with_pages.other_languages = ['fi']
    plan_with_pages.save()
    attribute_type = _action_type(plan_with_pages)
    form = admin_client.get(f'{TYPES_PATH}edit/{attribute_type.pk}/').context['form']
    assert 'action_list_filter_section' in form.fields
    assert 'show_in_reporting_tab' in form.fields
    assert 'scope_id' not in form.fields
    assert 'name_fi' in form.fields
    assert 'choice_options' in form.formsets


def test_category_type_edit_form(admin_client, category_type):
    attribute_type = AttributeTypeFactory.create(scope=category_type)
    form = admin_client.get(f'{TYPES_PATH}edit/{attribute_type.pk}/').context['form']
    assert 'scope_id' in form.fields
    assert 'action_list_filter_section' not in form.fields


def test_pledge_type_edit_form(admin_client, plan_with_pages):
    _enable_community_engagement(plan_with_pages)
    attribute_type = _pledge_type(plan_with_pages)
    form = admin_client.get(f'{TYPES_PATH}edit/{attribute_type.pk}/').context['form']
    assert 'show_in_reporting_tab' not in form.fields
    assert 'action_list_filter_section' not in form.fields


def test_format_is_read_only_once_values_exist(admin_client, plan_with_pages):
    attribute_type = _action_type(plan_with_pages, format=AttributeType.AttributeFormat.TEXT)
    path = f'{TYPES_PATH}edit/{attribute_type.pk}/'
    assert 'format' in admin_client.get(path).context['form'].fields
    AttributeTextFactory.create(type=attribute_type, content_object=ActionFactory.create(plan=plan_with_pages))
    response = admin_client.get(path)
    assert 'format' not in response.context['form'].fields
    assert 'This field already has values.' in response.content.decode()


def test_editing_type_saves_and_redirects_to_the_object_type(admin_client, plan_with_pages, action_ct):
    attribute_type = _action_type(plan_with_pages)
    path = f'{TYPES_PATH}edit/{attribute_type.pk}/?content_type={action_ct.pk}'
    data = post_data(admin_client.get(path).context['form'])
    data['name'] = 'Renamed'
    response = admin_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == _list_path(action_ct)
    attribute_type.refresh_from_db()
    assert attribute_type.name == 'Renamed'


def test_unarchiving_choice_option_redirects_to_edit(admin_client, plan_with_pages):
    attribute_type = _action_type(plan_with_pages, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    option = AttributeTypeChoiceOptionFactory.create(type=attribute_type)
    option.archive()
    edit_path = f'{TYPES_PATH}edit/{attribute_type.pk}/'
    assert f'{TYPES_PATH}{attribute_type.pk}/unarchive-choice-option/{option.pk}/' in admin_client.get(edit_path).content.decode()
    response = admin_client.post(f'{TYPES_PATH}{attribute_type.pk}/unarchive-choice-option/{option.pk}/')
    assert response.status_code == 302
    assert response['Location'] == edit_path
    option.refresh_from_db()
    assert option.is_active


def test_deleting_used_choice_option_archives_it(admin_client, plan_with_pages):
    attribute_type = _action_type(plan_with_pages, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    used = AttributeTypeChoiceOptionFactory.create(type=attribute_type, name='Used')
    kept = AttributeTypeChoiceOptionFactory.create(type=attribute_type, name='Kept')
    AttributeChoiceFactory.create(type=attribute_type, content_object=ActionFactory.create(plan=plan_with_pages), choice=used)
    path = f'{TYPES_PATH}edit/{attribute_type.pk}/'
    data = post_data(admin_client.get(path).context['form'])
    data['choice_options-0-DELETE'] = 'on'
    response = admin_client.post(path, data, follow=True)
    used.refresh_from_db()
    assert not used.is_active
    assert AttributeTypeChoiceOption.objects.filter(pk=kept.pk, is_active=True).exists()
    assert any("'Used'" in str(message) for message in response.context['messages'])


def test_other_plan_type_cannot_be_unarchived(admin_client):
    attribute_type = _action_type(PlanFactory.create(), format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    option = AttributeTypeChoiceOptionFactory.create(type=attribute_type)
    option.archive()
    admin_client.post(f'{TYPES_PATH}{attribute_type.pk}/unarchive-choice-option/{option.pk}/')
    option.refresh_from_db()
    assert not option.is_active


def test_delete_page_shows_usage(admin_client, plan_with_pages):
    attribute_type = _action_type(plan_with_pages, format=AttributeType.AttributeFormat.TEXT)
    action = ActionFactory.create(plan=plan_with_pages)
    AttributeTextFactory.create(type=attribute_type, content_object=action)
    response = admin_client.get(f'{TYPES_PATH}delete/{attribute_type.pk}/')
    assert response.status_code == 200
    assert response.context['usage_info'].published_object_names == [str(action)]


def test_deleting_type_redirects_to_the_object_type(admin_client, plan_with_pages, action_ct):
    attribute_type = _action_type(plan_with_pages)
    response = admin_client.post(f'{TYPES_PATH}delete/{attribute_type.pk}/?content_type={action_ct.pk}')
    assert response.status_code == 302
    assert response['Location'] == _list_path(action_ct)
    assert not AttributeType.objects.filter(pk=attribute_type.pk).exists()


def test_other_plan_type_cannot_be_changed(admin_client):
    attribute_type = _action_type(PlanFactory.create())
    assert admin_client.get(f'{TYPES_PATH}edit/{attribute_type.pk}/').status_code == 302
    admin_client.post(f'{TYPES_PATH}delete/{attribute_type.pk}/')
    assert AttributeType.objects.filter(pk=attribute_type.pk).exists()


def test_choice_options_keep_their_order(admin_client, plan_with_pages):
    attribute_type = _action_type(plan_with_pages, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    first = AttributeTypeChoiceOptionFactory.create(type=attribute_type, name='First')
    second = AttributeTypeChoiceOptionFactory.create(type=attribute_type, name='Second')
    path = f'{TYPES_PATH}edit/{attribute_type.pk}/'
    data = post_data(admin_client.get(path).context['form'])
    data['choice_options-0-ORDER'], data['choice_options-1-ORDER'] = '2', '1'
    assert admin_client.post(path, data).status_code == 302
    names = list(
        AttributeTypeChoiceOption.objects
        .filter(type=attribute_type, is_active=True)
        .order_by('order')
        .values_list('name', flat=True)
    )
    assert names == [second.name, first.name]
