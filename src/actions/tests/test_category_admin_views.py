"""The category type and category admin views."""

from __future__ import annotations

import html
import re

from reversion.models import Version

import pytest

from actions.models import Category, CategoryType
from actions.tests.factories import (
    AttributeTypeFactory,
    CategoryFactory,
    CategoryTypeFactory,
    CommonCategoryFactory,
    PlanFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data, submenu_links
from pages.models import CategoryPage, CategoryTypePage
from pages.tests.factories import CategoryPageFactory, CategoryTypePageFactory

pytestmark = pytest.mark.django_db

TYPES_PATH = '/admin/actions/categorytype/'
CATEGORIES_PATH = '/admin/actions/category/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def superuser_client(client, plan_with_pages, superuser):
    ClientPlanFactory.create(plan=plan_with_pages)
    superuser.selected_admin_plan = plan_with_pages
    superuser.save(update_fields=['selected_admin_plan'])
    client.force_login(superuser)
    return client


@pytest.fixture
def category_type(plan_with_pages):
    return CategoryTypeFactory.create(plan=plan_with_pages, name='Themes', common=None)


@pytest.fixture
def other_plan_category_type():
    return CategoryTypeFactory.create(plan=PlanFactory.create(), name='Other plan themes', common=None)


def _categories_path(category_type: CategoryType) -> str:
    return f'{CATEGORIES_PATH}?category_type={category_type.pk}'


def _category(category_type: CategoryType, **kwargs) -> Category:
    return CategoryFactory.create(type=category_type, common=None, **kwargs)


def _add_path(response_content: bytes, base_path: str) -> str:
    match = re.search(rf'href="({base_path}(?:create|add)/[^"]*)"', response_content.decode())
    assert match is not None
    return html.unescape(match.group(1))


def test_settings_menu_links_category_types(admin_client):
    links = submenu_links(admin_client.get('/admin/account/').content, 'Settings')
    assert ('Category types', TYPES_PATH) in links


def test_categories_menu_lists_active_plan_types(admin_client, category_type, other_plan_category_type):
    links = submenu_links(admin_client.get('/admin/account/').content, 'Categories')
    assert links == [('Themes', _categories_path(category_type))]


def test_contact_person_has_no_access(client, plan_with_pages, action_contact_person_user, category_type):
    ClientPlanFactory.create(plan=plan_with_pages)
    category = _category(category_type)
    client.force_login(action_contact_person_user)
    assert submenu_links(client.get('/admin/account/').content, 'Categories') == []
    for path in (TYPES_PATH, f'{TYPES_PATH}edit/{category_type.pk}/', f'{CATEGORIES_PATH}edit/{category.pk}/'):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response['Location'] == '/admin/', path


def test_type_listing_shows_active_plan_types(admin_client, category_type, other_plan_category_type):
    content = admin_client.get(TYPES_PATH).content.decode()
    assert f'{TYPES_PATH}edit/{category_type.pk}/' in content
    assert f'{TYPES_PATH}edit/{other_plan_category_type.pk}/' not in content


def test_creating_type_uses_active_plan(admin_client, plan_with_pages):
    add_path = _add_path(admin_client.get(TYPES_PATH).content, TYPES_PATH)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({'name': 'Sectors', 'identifier': 'sectors'})
    response = admin_client.post(add_path, data)
    assert response.status_code == 302
    assert CategoryType.objects.get(identifier='sectors').plan == plan_with_pages


def test_type_identifier_is_unique_within_plan(admin_client, category_type):
    add_path = _add_path(admin_client.get(TYPES_PATH).content, TYPES_PATH)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({'name': 'Duplicate', 'identifier': category_type.identifier})
    response = admin_client.post(add_path, data)
    assert response.status_code == 200
    assert 'identifier' in response.context['form'].errors


def test_type_translation_tabs_follow_active_plan(admin_client, plan_with_pages, category_type):
    plan_with_pages.other_languages = ['fi']
    plan_with_pages.save()
    form = admin_client.get(f'{TYPES_PATH}edit/{category_type.pk}/').context['form']
    assert 'name_fi' in form.fields
    assert 'name_de' not in form.fields
    assert 'levels' in form.formsets


def test_type_common_field_is_read_only(admin_client, plan_with_pages, category_type):
    form = admin_client.get(f'{TYPES_PATH}edit/{category_type.pk}/').context['form']
    assert 'common' not in form.fields
    common_type = CategoryTypeFactory.create(plan=plan_with_pages)
    form = admin_client.get(f'{TYPES_PATH}edit/{common_type.pk}/').context['form']
    assert form.fields['common'].disabled


def test_editing_type_records_revision(admin_client, plan_admin_user, category_type):
    path = f'{TYPES_PATH}edit/{category_type.pk}/'
    data = post_data(admin_client.get(path).context['form'])
    data['name'] = 'Sectors'
    response = admin_client.post(path, data)
    assert response.status_code == 302
    category_type.refresh_from_db()
    assert category_type.name == 'Sectors'
    version = Version.objects.get_for_object(category_type).get()
    assert version.revision.user == plan_admin_user


def test_other_plan_type_cannot_be_changed(admin_client, other_plan_category_type):
    assert admin_client.get(f'{TYPES_PATH}edit/{other_plan_category_type.pk}/').status_code == 302
    admin_client.post(f'{TYPES_PATH}delete/{other_plan_category_type.pk}/')
    assert CategoryType.objects.filter(pk=other_plan_category_type.pk).exists()


def test_deleting_type_unlinks_common_type_and_deletes_pages(admin_client, plan_with_pages):
    category_type = CategoryTypeFactory.create(plan=plan_with_pages)
    assert category_type.common is not None
    plan_with_pages.common_category_types.add(category_type.common)
    page = CategoryTypePageFactory.create(parent=plan_with_pages.root_page, category_type=category_type)
    response = admin_client.post(f'{TYPES_PATH}delete/{category_type.pk}/')
    assert response.status_code == 302
    assert not CategoryType.objects.filter(pk=category_type.pk).exists()
    assert not plan_with_pages.common_category_types.filter(pk=category_type.common.pk).exists()
    assert not CategoryTypePage.objects.filter(pk=page.pk).exists()


def test_category_listing_shows_only_the_type(admin_client, plan_with_pages, category_type, other_plan_category_type):
    category = _category(category_type)
    other_type_category = _category(CategoryTypeFactory.create(plan=plan_with_pages, common=None))
    other_plan_category = _category(other_plan_category_type)
    content = admin_client.get(_categories_path(category_type)).content.decode()
    assert f'{CATEGORIES_PATH}edit/{category.pk}/' in content
    assert f'{CATEGORIES_PATH}edit/{other_type_category.pk}/' not in content
    assert f'{CATEGORIES_PATH}edit/{other_plan_category.pk}/' not in content


def test_listings_offer_no_bulk_delete(admin_client, category_type):
    _category(category_type)
    for path in (TYPES_PATH, _categories_path(category_type)):
        assert 'data-bulk-action-checkbox' not in admin_client.get(path).content.decode(), path


def test_creating_category_gets_type_from_query(admin_client, category_type):
    add_path = _add_path(admin_client.get(_categories_path(category_type)).content, CATEGORIES_PATH)
    assert f'category_type={category_type.pk}' in add_path
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({'name': 'Energy', 'identifier': 'energy'})
    response = admin_client.post(add_path, data)
    assert response.status_code == 302
    assert Category.objects.get(identifier='energy').type == category_type


def test_creating_category_generates_hidden_identifier(admin_client, category_type):
    category_type.hide_category_identifiers = True
    category_type.save()
    add_path = _add_path(admin_client.get(_categories_path(category_type)).content, CATEGORIES_PATH)
    form = admin_client.get(add_path).context['form']
    assert 'identifier' not in form.fields
    data = post_data(form)
    data['name'] = 'Energy'
    assert admin_client.post(add_path, data).status_code == 302
    assert Category.objects.get(name='Energy').identifier


def test_category_identifier_is_unique_within_type(admin_client, category_type):
    existing = _category(category_type)
    add_path = _add_path(admin_client.get(_categories_path(category_type)).content, CATEGORIES_PATH)
    data = post_data(admin_client.get(add_path).context['form'])
    data.update({'name': 'Energy', 'identifier': existing.identifier})
    response = admin_client.post(add_path, data)
    assert response.status_code == 200
    assert 'identifier' in response.context['form'].errors


def test_category_edit_form(admin_client, plan_with_pages, category_type):
    category = _category(category_type)
    sibling = _category(category_type)
    other_type_category = _category(CategoryTypeFactory.create(plan=plan_with_pages, common=None))
    attribute_type = AttributeTypeFactory.create(scope=category_type)
    form = admin_client.get(f'{CATEGORIES_PATH}edit/{category.pk}/').context['form']
    parents = set(form.fields['parent'].queryset)
    assert sibling in parents
    assert other_type_category not in parents
    assert f'attribute_type_{attribute_type.pk}' in form.fields
    assert 'indicator_relationships' in form.formsets
    assert 'icons' not in form.formsets
    assert 'kausal_paths_node_uuid' not in form.fields


def test_superuser_category_edit_form(superuser_client, category_type):
    category = _category(category_type)
    form = superuser_client.get(f'{CATEGORIES_PATH}edit/{category.pk}/').context['form']
    assert 'icons' in form.formsets
    assert 'kausal_paths_node_uuid' in form.fields


def test_common_category_instance_fields_are_read_only(admin_client, category_type):
    category = CategoryFactory.create(type=category_type, common=CommonCategoryFactory.create())
    form = admin_client.get(f'{CATEGORIES_PATH}edit/{category.pk}/').context['form']
    assert form.fields['identifier'].disabled
    assert form.fields['parent'].disabled


def test_editing_category_records_revision(admin_client, plan_admin_user, category_type):
    category = _category(category_type)
    path = f'{CATEGORIES_PATH}edit/{category.pk}/?category_type={category_type.pk}'
    data = post_data(admin_client.get(path).context['form'])
    data['name'] = 'Energy'
    response = admin_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == _categories_path(category_type)
    category.refresh_from_db()
    assert category.name == 'Energy'
    version = Version.objects.get_for_object(category).get()
    assert version.revision.user == plan_admin_user


def test_editing_category_offers_change_log_message(admin_client, plan_with_pages, category_type):
    plan_with_pages.features.enable_change_log = True
    plan_with_pages.features.save()
    category = _category(category_type)
    path = f'{CATEGORIES_PATH}edit/{category.pk}/'
    data = post_data(admin_client.get(path).context['form'])
    response = admin_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == f'/admin/snippets/actions/categorychangelogmessage/add/?category={category.pk}'


@pytest.fixture
def not_editable_category(category_type):
    category_type.instances_editable_by = CategoryType.EditableBy.NOT_EDITABLE
    category_type.save()
    return _category(category_type)


def test_not_editable_type_refuses_plan_admin(admin_client, category_type, not_editable_category):
    for path in (
        f'{CATEGORIES_PATH}edit/{not_editable_category.pk}/',
        f'{CATEGORIES_PATH}create/?category_type={category_type.pk}',
    ):
        assert admin_client.get(path).status_code == 302, path
    admin_client.post(f'{CATEGORIES_PATH}delete/{not_editable_category.pk}/')
    assert Category.objects.filter(pk=not_editable_category.pk).exists()


def test_not_editable_type_allows_superuser(superuser_client, not_editable_category):
    assert superuser_client.get(f'{CATEGORIES_PATH}edit/{not_editable_category.pk}/').status_code == 200


def test_other_plan_category_cannot_be_edited(admin_client, other_plan_category_type):
    category = _category(other_plan_category_type)
    assert admin_client.get(f'{CATEGORIES_PATH}edit/{category.pk}/').status_code == 302


def test_deleting_category_deletes_its_pages(admin_client, plan_with_pages, category_type):
    category = _category(category_type)
    type_page = CategoryTypePageFactory.create(parent=plan_with_pages.root_page, category_type=category_type)
    page = CategoryPageFactory.create(parent=type_page, category=category)
    response = admin_client.post(f'{CATEGORIES_PATH}delete/{category.pk}/?category_type={category_type.pk}')
    assert response.status_code == 302
    assert response['Location'] == _categories_path(category_type)
    assert not Category.objects.filter(pk=category.pk).exists()
    assert not CategoryPage.objects.filter(pk=page.pk).exists()
