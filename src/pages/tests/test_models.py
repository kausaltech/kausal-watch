from __future__ import annotations

from wagtail.models import Page

import pytest

from actions.models import Plan
from documentation.models import DocumentationPage, DocumentationRootPage
from orgs.tests.factories import OrganizationFactory
from pages.models import ActionListPage

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    'field_name',
    [
        'primary_filters',
        'main_filters',
        'advanced_filters',
        'details_main_top',
        'details_main_bottom',
        'details_aside',
    ],
)
def test_action_list_page_contains_attribute_type(plan_with_pages, action_attribute_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.contains_model_instance_block(action_attribute_type, field_name)
    setattr(page, field_name, [('attribute', {'attribute_type': action_attribute_type})])
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(action_attribute_type, field_name)


@pytest.mark.parametrize('field_name', ['primary_filters', 'main_filters', 'advanced_filters'])
def test_action_list_page_category_type_in_filters(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.contains_model_instance_block(category_type, field_name)
    setattr(page, field_name, [('category', {'category_type': category_type})])
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(category_type, field_name)


@pytest.mark.parametrize('field_name', ['details_main_top', 'details_main_bottom', 'details_aside'])
def test_action_list_page_category_type_in_details(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.contains_model_instance_block(category_type, field_name)
    setattr(page, field_name, [('categories', {'category_type': category_type})])
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(category_type, field_name)


@pytest.mark.parametrize(
    'field_name',
    [
        'primary_filters',
        'main_filters',
        'advanced_filters',
        'details_main_top',
        'details_main_bottom',
        'details_aside',
    ],
)
def test_action_list_page_insert_attribute_type(plan_with_pages, attribute_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.contains_model_instance_block(attribute_type, field_name)
    page.insert_model_instance_block(attribute_type, field_name)
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(attribute_type, field_name)


@pytest.mark.parametrize(
    'field_name',
    [
        'primary_filters',
        'main_filters',
        'advanced_filters',
        'details_main_top',
        'details_main_bottom',
        'details_aside',
    ],
)
def test_action_list_page_insert_category_type(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.contains_model_instance_block(category_type, field_name)
    page.insert_model_instance_block(category_type, field_name)
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(category_type, field_name)


@pytest.mark.parametrize(
    'field_name',
    [
        'primary_filters',
        'main_filters',
        'advanced_filters',
        'details_main_top',
        'details_main_bottom',
        'details_aside',
    ],
)
def test_action_list_page_remove_attribute_type(plan_with_pages, action_attribute_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    page.insert_model_instance_block(action_attribute_type, field_name)
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(action_attribute_type, field_name)
    page.remove_model_instance_block(action_attribute_type, field_name)
    page.save()
    page.refresh_from_db()
    assert not page.contains_model_instance_block(action_attribute_type, field_name)


@pytest.mark.parametrize(
    'field_name',
    [
        'primary_filters',
        'main_filters',
        'advanced_filters',
        'details_main_top',
        'details_main_bottom',
        'details_aside',
    ],
)
def test_action_list_page_remove_category_type(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    page.insert_model_instance_block(category_type, field_name)
    page.save()
    page.refresh_from_db()
    assert page.contains_model_instance_block(category_type, field_name)
    page.remove_model_instance_block(category_type, field_name)
    page.save()
    page.refresh_from_db()
    assert not page.contains_model_instance_block(category_type, field_name)


def _create_plan_with_translated_pages(django_capture_on_commit_callbacks) -> Plan:
    # wagtail-localize publishes the translations in `on_commit` callbacks
    with django_capture_on_commit_callbacks(execute=True):
        return Plan.create_with_defaults(
            identifier='tree-test',
            name='Tree test',
            primary_language='da',
            other_languages=['en'],
            organization=OrganizationFactory.create(),
        )


def _count_children(page: Page) -> int:
    # Not `page.get_children()`, which returns nothing if `numchild` is 0
    return Page.objects.filter(path__startswith=page.path, depth=page.depth + 1).count()


def test_create_plan_sets_numchild_of_translated_root_page(django_capture_on_commit_callbacks):
    plan = _create_plan_with_translated_pages(django_capture_on_commit_callbacks)
    for root_page in plan.root_page.get_translations(inclusive=True):
        assert _count_children(root_page) == 4
        assert root_page.numchild == 4


def test_page_delete_removes_children_despite_stale_numchild(django_capture_on_commit_callbacks):
    plan = _create_plan_with_translated_pages(django_capture_on_commit_callbacks)
    translated_root_page = plan.root_page.get_translations().get().specific
    Page.objects.filter(pk=translated_root_page.pk).update(numchild=0)
    translated_root_page.numchild = 0

    translated_root_page.delete()

    assert not Page.objects.filter(path__startswith=translated_root_page.path).exists()
    assert Page.find_problems() == ([], [], [], [], [])


def test_plan_delete_removes_pages_despite_stale_numchild(django_capture_on_commit_callbacks):
    plan = _create_plan_with_translated_pages(django_capture_on_commit_callbacks)
    global_root = Page.get_first_root_node()
    assert global_root is not None
    documentation_root_page = global_root.add_child(
        instance=DocumentationRootPage(title='Documentation', plan=plan, slug='docs'),
    )
    documentation_root_page.add_child(instance=DocumentationPage(title='Documentation page'))
    root_page_paths = [
        *(page.path for page in plan.root_page.get_translations(inclusive=True)),
        documentation_root_page.path,
    ]
    Page.objects.filter(path__in=root_page_paths).update(numchild=0)

    plan.delete()

    for path in root_page_paths:
        assert not Page.objects.filter(path__startswith=path).exists()
    assert Page.find_problems() == ([], [], [], [], [])


def test_page_delete_removes_children_despite_stale_path(django_capture_on_commit_callbacks):
    plan = _create_plan_with_translated_pages(django_capture_on_commit_callbacks)
    translated_root_page = plan.root_page.get_translations().get().specific
    current_path = translated_root_page.path
    Page.objects.filter(pk=translated_root_page.pk).update(numchild=0)
    # As if the page had been moved through another instance
    translated_root_page.path = Page._get_path(None, 1, 9999)

    translated_root_page.delete()

    assert not Page.objects.filter(path__startswith=current_path).exists()
    assert Page.find_problems() == ([], [], [], [], [])
