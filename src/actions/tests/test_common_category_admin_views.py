"""The common category type and common category admin views."""

from __future__ import annotations

import html
import re

from reversion.models import Version
from wagtail.models import ModelLogEntry

import pytest

from actions.models import Category, CommonCategory, CommonCategoryType
from actions.tests.factories import CategoryTypeFactory, CommonCategoryFactory, CommonCategoryTypeFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data, submenu_links

pytestmark = pytest.mark.django_db

TYPES_PATH = '/admin/actions/commoncategorytype/'
CATEGORIES_PATH = '/admin/actions/commoncategory/'


@pytest.fixture
def superuser_client(client, plan_with_pages, superuser):
    ClientPlanFactory.create(plan=plan_with_pages)
    superuser.selected_admin_plan = plan_with_pages
    superuser.save(update_fields=['selected_admin_plan'])
    client.force_login(superuser)
    return client


@pytest.fixture
def common_category_type():
    return CommonCategoryTypeFactory.create(name='Goals')


def _categories_path(common_category_type: CommonCategoryType) -> str:
    return f'{CATEGORIES_PATH}?common_category_type={common_category_type.pk}'


def _add_path(response_content: bytes, base_path: str) -> str:
    match = re.search(rf'href="({base_path}(?:create|add)/[^"]*)"', response_content.decode())
    assert match is not None
    return html.unescape(match.group(1))


def _move_after(client, category: CommonCategory, after: CommonCategory):
    return client.get(f'{CATEGORIES_PATH}reorder/{category.pk}/?common_category_type={category.type.pk}&after={after.pk}')


def _orders(common_category_type: CommonCategoryType) -> list[int]:
    return list(common_category_type.categories.order_by('order').values_list('pk', flat=True))


def test_common_categories_menu_lists_types(superuser_client, common_category_type):
    other_type = CommonCategoryTypeFactory.create(name='Themes')
    links = submenu_links(superuser_client.get('/admin/account/').content, 'Common categories')
    assert ('Goals', _categories_path(common_category_type)) in links
    assert ('Themes', _categories_path(other_type)) in links


def test_settings_menu_links_common_category_types(superuser_client):
    links = submenu_links(superuser_client.get('/admin/account/').content, 'Settings')
    assert ('Common category types', TYPES_PATH) in links


def test_plan_admin_has_no_access(client, plan_with_pages, plan_admin_user, common_category_type):
    ClientPlanFactory.create(plan=plan_with_pages)
    category = CommonCategoryFactory.create(type=common_category_type)
    client.force_login(plan_admin_user)
    assert submenu_links(client.get('/admin/account/').content, 'Common categories') == []
    for path in (
        TYPES_PATH,
        f'{TYPES_PATH}edit/{common_category_type.pk}/',
        _categories_path(common_category_type),
        f'{CATEGORIES_PATH}edit/{category.pk}/',
    ):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response['Location'] == '/admin/', path


def test_type_listing(superuser_client, common_category_type):
    content = superuser_client.get(TYPES_PATH).content.decode()
    assert f'{TYPES_PATH}edit/{common_category_type.pk}/' in content


def test_category_listing_shows_only_the_type(superuser_client, common_category_type):
    category = CommonCategoryFactory.create(type=common_category_type)
    other_category = CommonCategoryFactory.create()
    content = superuser_client.get(_categories_path(common_category_type)).content.decode()
    assert f'{CATEGORIES_PATH}edit/{category.pk}/' in content
    assert f'{CATEGORIES_PATH}edit/{other_category.pk}/' not in content


def test_listings_offer_no_bulk_delete(superuser_client, common_category_type):
    CommonCategoryFactory.create(type=common_category_type)
    for path in (TYPES_PATH, _categories_path(common_category_type)):
        assert 'data-bulk-action-checkbox' not in superuser_client.get(path).content.decode(), path


def test_creating_type(superuser_client):
    add_path = _add_path(superuser_client.get(TYPES_PATH).content, TYPES_PATH)
    data = post_data(superuser_client.get(add_path).context['form'])
    data.update({'name': 'Targets', 'identifier': 'targets'})
    response = superuser_client.post(add_path, data)
    assert response.status_code == 302
    assert CommonCategoryType.objects.filter(identifier='targets', name='Targets').exists()


def test_type_translation_tabs_follow_active_plan(superuser_client, plan_with_pages, common_category_type):
    plan_with_pages.other_languages = ['fi']
    plan_with_pages.save()
    form = superuser_client.get(f'{TYPES_PATH}edit/{common_category_type.pk}/').context['form']
    assert 'name_fi' in form.fields
    assert 'name_de' not in form.fields


def test_editing_type_records_revision(superuser_client, superuser, common_category_type):
    path = f'{TYPES_PATH}edit/{common_category_type.pk}/'
    data = post_data(superuser_client.get(path).context['form'])
    data['name'] = 'Objectives'
    response = superuser_client.post(path, data)
    assert response.status_code == 302
    common_category_type.refresh_from_db()
    assert common_category_type.name == 'Objectives'
    version = Version.objects.get_for_object(common_category_type).get()
    assert version.revision.user == superuser
    assert ModelLogEntry.objects.get(object_id=str(common_category_type.pk), action='wagtail.edit').user == superuser


def test_creating_category_instantiates_it_for_plans(superuser_client, plan_with_pages, common_category_type):
    plan_with_pages.common_category_types.add(common_category_type)
    category_type = CategoryTypeFactory.create(plan=plan_with_pages, common=common_category_type)
    add_path = _add_path(superuser_client.get(_categories_path(common_category_type)).content, CATEGORIES_PATH)
    data = post_data(superuser_client.get(add_path).context['form'])
    data.update({'name': 'Clean water', 'identifier': 'water'})
    response = superuser_client.post(add_path, data)
    assert response.status_code == 302
    category = CommonCategory.objects.get(identifier='water')
    assert category.type == common_category_type
    assert list(Category.objects.filter(common=category).values_list('type', flat=True)) == [category_type.pk]


def test_category_edit_form(superuser_client, common_category_type):
    category = CommonCategoryFactory.create(type=common_category_type)
    form = superuser_client.get(f'{CATEGORIES_PATH}edit/{category.pk}/').context['form']
    assert form.fields['identifier'].disabled
    assert 'icons' in form.formsets
    assert {'name_fi', 'name_de'} <= set(form.fields)


def test_editing_category_records_revision(superuser_client, superuser, common_category_type):
    category = CommonCategoryFactory.create(type=common_category_type, identifier='water')
    path = f'{CATEGORIES_PATH}edit/{category.pk}/'
    data = post_data(superuser_client.get(path).context['form'])
    data.update({'name': 'Clean water', 'name_fi': 'Puhdas vesi', 'identifier': 'changed'})
    response = superuser_client.post(path, data)
    assert response.status_code == 302
    category.refresh_from_db()
    assert category.name == 'Clean water'
    assert category.name_fi == 'Puhdas vesi'  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    assert category.identifier == 'water'
    version = Version.objects.get_for_object(category).get()
    assert version.revision.user == superuser
    assert ModelLogEntry.objects.get(object_id=str(category.pk), action='wagtail.edit').user == superuser


def test_reordering_stays_within_type(superuser_client, common_category_type):
    first, second, third = (CommonCategoryFactory.create(type=common_category_type) for _ in range(3))
    other_type = CommonCategoryTypeFactory.create()
    others = [CommonCategoryFactory.create(type=other_type) for _ in range(3)]
    response = _move_after(superuser_client, first, second)
    assert response.status_code == 200
    assert _orders(common_category_type) == [second.pk, first.pk, third.pk]
    assert _orders(other_type) == [o.pk for o in others]


def test_deleting_category(superuser_client, common_category_type):
    category = CommonCategoryFactory.create(type=common_category_type)
    response = superuser_client.post(f'{CATEGORIES_PATH}delete/{category.pk}/')
    assert response.status_code == 302
    assert not CommonCategory.objects.filter(pk=category.pk).exists()


def test_deleting_type(superuser_client, common_category_type):
    response = superuser_client.post(f'{TYPES_PATH}delete/{common_category_type.pk}/')
    assert response.status_code == 302
    assert not CommonCategoryType.objects.filter(pk=common_category_type.pk).exists()
