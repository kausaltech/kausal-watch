import pytest

from pages.models import ActionListPage

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('field_name', [
    'primary_filters', 'main_filters', 'advanced_filters', 'details_main_top', 'details_main_bottom', 'details_aside'
])
def test_action_list_page_references_attribute_type(plan_with_pages, attribute_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.references_attribute_type(attribute_type, field_name)
    setattr(page, field_name, [('attribute', {'attribute_type': attribute_type})])
    page.save()
    page.refresh_from_db()
    assert page.references_attribute_type(attribute_type, field_name)


@pytest.mark.parametrize('field_name', ['primary_filters', 'main_filters', 'advanced_filters'])
def test_action_list_page_category_type_in_filters(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.references_category_type(category_type, field_name)
    setattr(page, field_name, [('category', {'category_type': category_type})])
    page.save()
    page.refresh_from_db()
    assert page.references_category_type(category_type, field_name)


@pytest.mark.parametrize('field_name', ['details_main_top', 'details_main_bottom', 'details_aside'])
def test_action_list_page_category_type_in_details(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.references_category_type(category_type, field_name)
    setattr(page, field_name, [('categories', {'category_type': category_type})])
    page.save()
    page.refresh_from_db()
    assert page.references_category_type(category_type, field_name)


@pytest.mark.parametrize('field_name', [
    'primary_filters', 'main_filters', 'advanced_filters', 'details_main_top', 'details_main_bottom', 'details_aside'
])
def test_action_list_page_insert_attribute_type(plan_with_pages, attribute_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.references_attribute_type(attribute_type, field_name)
    page.insert_attribute_type(attribute_type, field_name)
    page.save()
    page.refresh_from_db()
    assert page.references_attribute_type(attribute_type, field_name)


@pytest.mark.parametrize('field_name', [
    'primary_filters', 'main_filters', 'advanced_filters', 'details_main_top', 'details_main_bottom', 'details_aside'
])
def test_action_list_page_insert_category_type(plan_with_pages, category_type, field_name):
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    assert not page.references_category_type(category_type, field_name)
    page.insert_category_type(category_type, field_name)
    page.save()
    page.refresh_from_db()
    assert page.references_category_type(category_type, field_name)
