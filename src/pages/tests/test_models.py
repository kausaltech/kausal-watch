import datetime

from django.utils.timezone import make_aware

import pytest

from actions.tests.factories import PlanDomainFactory, PlanFactory
from pages.models import ActionListPage
from pages.tests.factories import StaticPageFactory

pytestmark = pytest.mark.django_db

PUBLISHED_AT = make_aware(datetime.datetime(2021, 1, 1))  # noqa: DTZ001


@pytest.fixture
def published_url_plan(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    plan = PlanFactory.create(
        identifier='myplan',
        primary_language='en',
        other_languages=['fi'],
        published_at=PUBLISHED_AT,
    )
    plan.create_default_site()
    plan.save()
    return plan


class TestGetUrlParts:
    """AplansPage.get_url_parts must reuse Plan.get_view_url's canonical resolution."""

    def test_published_plan_uses_plan_domain_with_base_path(self, published_url_plan):
        from actions.models.plan import PlanDomain

        PlanDomainFactory.create(
            plan=published_url_plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        page = StaticPageFactory.create(parent=published_url_plan.root_page)
        site_id, root_url, page_path = page.get_url_parts()
        assert site_id == published_url_plan.site_id
        assert root_url == 'https://city.gov/climate'
        assert page_path == page.url_path

    def test_published_plan_prefers_production_plan_domain_over_wildcard(self, published_url_plan):
        from actions.models.plan import PlanDomain

        PlanDomainFactory.create(
            plan=published_url_plan,
            hostname='climate.city.gov',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        page = StaticPageFactory.create(parent=published_url_plan.root_page)
        _, root_url, _ = page.get_url_parts()
        assert root_url == 'https://climate.city.gov'

    def test_unpublished_plan_ignores_production_plan_domain(self, settings):
        from actions.models.plan import PlanDomain

        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            published_at=None,
        )
        plan.create_default_site()
        plan.save()
        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        page = StaticPageFactory.create(parent=plan.root_page)
        _, root_url, _ = page.get_url_parts()
        assert root_url == 'https://myplan.example.com'

    def test_falls_back_to_wildcard_hostname(self, published_url_plan):
        page = StaticPageFactory.create(parent=published_url_plan.root_page)
        _, root_url, _ = page.get_url_parts()
        assert root_url == 'https://myplan.example.com'

    def test_returns_none_when_hostname_unresolvable(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(identifier='myplan', primary_language='en', published_at=PUBLISHED_AT)
        plan.create_default_site()
        plan.save()
        settings.HOSTNAME_PLAN_DOMAINS = []
        settings.DEPLOYMENT_TYPE = 'production'
        page = StaticPageFactory.create(parent=plan.root_page)
        assert page.get_url_parts() is None


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
