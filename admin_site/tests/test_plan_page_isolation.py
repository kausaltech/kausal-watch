"""
Tests for multi-tenant plan admin console page isolation.

Verifies that the Wagtail admin page explorer only shows pages
belonging to the active plan's site, and that the ``_wagtail_site``
attribute on the request is respected by the explorer hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.test import RequestFactory
from wagtail.models import Page

import factory
import pytest

from actions.tests.factories import PlanFactory
from pages.tests.factories import StaticPageFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_plan_with_site(name: str, identifier: str) -> Plan:
    from actions.perms import sync_all_group_permissions_for_plan

    plan = PlanFactory.create(name=name, identifier=identifier)
    plan.create_default_site()
    plan.save()
    sync_all_group_permissions_for_plan(plan)
    return plan


@pytest.fixture
@factory.django.mute_signals(post_save)
def plan_a(settings) -> Plan:
    """First plan with its own Wagtail site and page tree."""
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    return _create_plan_with_site('Plan A', 'plan-a')


@pytest.fixture
@factory.django.mute_signals(post_save)
def plan_b(settings) -> Plan:
    """Second plan with its own Wagtail site and page tree."""
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    return _create_plan_with_site('Plan B', 'plan-b')


@pytest.fixture
def plan_a_child_page(plan_a: Plan) -> Page:
    return StaticPageFactory.create(parent=plan_a.root_page, title='Plan A child')


@pytest.fixture
def plan_b_child_page(plan_b: Plan) -> Page:
    return StaticPageFactory.create(parent=plan_b.root_page, title='Plan B child')


def _create_plan_admin(plan: Plan) -> User:
    from actions.perms import add_plan_admin_perms

    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan])
    add_plan_admin_perms(user)
    return user


@pytest.fixture
def admin_user_a(plan_a: Plan) -> User:
    """Admin user who administers Plan A."""
    return _create_plan_admin(plan_a)


@pytest.fixture
def admin_user_b(plan_b: Plan) -> User:
    """Admin user who administers Plan B."""
    return _create_plan_admin(plan_b)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_explorer_pages(user: User, parent_page: Page) -> list[Page]:
    """Invoke the ``restrict_pages_to_plan`` hook and return the filtered pages."""
    from admin_site.wagtail_hooks import restrict_pages_to_plan

    all_pages = Page.objects.all()
    request = RequestFactory().get('/admin/pages/')
    request.user = user
    return list(restrict_pages_to_plan(parent_page, all_pages, request))


# ---------------------------------------------------------------------------
# Tests - site isolation
# ---------------------------------------------------------------------------


class TestPlanSiteIsolation:
    def test_plans_have_distinct_sites(self, plan_a: Plan, plan_b: Plan):
        assert plan_a.site is not None
        assert plan_b.site is not None
        assert plan_a.site.pk != plan_b.site.pk

    def test_plans_have_distinct_root_pages(self, plan_a: Plan, plan_b: Plan):
        assert plan_a.root_page.pk != plan_b.root_page.pk

    def test_plan_site_hostname_derived_from_default_hostname(self, plan_a: Plan):
        assert plan_a.site is not None
        assert plan_a.site.hostname == 'plan-a.example.com'

    def test_create_default_site_uses_default_hostname(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['correct-domain.io']
        plan = PlanFactory.create(identifier='testplan')
        plan.create_default_site()
        plan.save()
        assert plan.site is not None
        assert plan.site.hostname == 'testplan.correct-domain.io'


# ---------------------------------------------------------------------------
# Tests - page explorer filtering
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures('plan_b_child_page')
class TestPageExplorerFiltering:
    def test_admin_sees_own_plan_root_and_child(
        self,
        plan_a: Plan,
        plan_a_child_page: Page,
        admin_user_a: User,
    ):
        pages = _get_explorer_pages(admin_user_a, plan_a.root_page)
        page_ids = {p.pk for p in pages}
        assert plan_a.root_page.pk in page_ids
        assert plan_a_child_page.pk in page_ids

    def test_admin_does_not_see_other_plan_pages(
        self,
        plan_a: Plan,
        plan_b: Plan,
        plan_b_child_page: Page,
        admin_user_a: User,
    ):
        pages = _get_explorer_pages(admin_user_a, plan_a.root_page)
        page_ids = {p.pk for p in pages}
        assert plan_b.root_page.pk not in page_ids
        assert plan_b_child_page.pk not in page_ids

    def test_other_admin_sees_only_own_pages(
        self,
        plan_a: Plan,
        plan_b: Plan,
        plan_a_child_page: Page,
        plan_b_child_page: Page,
        admin_user_b: User,
    ):
        pages = _get_explorer_pages(admin_user_b, plan_b.root_page)
        page_ids = {p.pk for p in pages}
        assert plan_b.root_page.pk in page_ids
        assert plan_b_child_page.pk in page_ids
        assert plan_a.root_page.pk not in page_ids
        assert plan_a_child_page.pk not in page_ids


# ---------------------------------------------------------------------------
# Tests - full HTTP admin view
# ---------------------------------------------------------------------------


class TestAdminPageExplorerView:
    def test_admin_explorer_returns_200(
        self,
        client,
        plan_a: Plan,
        admin_user_a: User,
    ):
        client.force_login(admin_user_a)
        response = client.get(f'/admin/pages/{plan_a.root_page.pk}/')
        assert response.status_code == 200

    def test_admin_explorer_contains_own_child_page(
        self,
        client,
        plan_a: Plan,
        plan_a_child_page: Page,
        admin_user_a: User,
    ):
        client.force_login(admin_user_a)
        response = client.get(f'/admin/pages/{plan_a.root_page.pk}/')
        assert plan_a_child_page.title.encode() in response.content

    @pytest.mark.usefixtures('plan_a_child_page')
    def test_admin_explorer_excludes_other_plan_child_page(
        self,
        client,
        plan_a: Plan,
        plan_b_child_page: Page,
        admin_user_a: User,
    ):
        client.force_login(admin_user_a)
        response = client.get(f'/admin/pages/{plan_a.root_page.pk}/')
        assert plan_b_child_page.title.encode() not in response.content


# ---------------------------------------------------------------------------
# Tests - cross-plan access denied
# ---------------------------------------------------------------------------


class TestCrossPlanAccessDenied:
    """Verify that an admin cannot edit or usefully browse pages from the other plan."""

    def test_editing_other_plans_root_page_is_denied(
        self,
        client,
        plan_b: Plan,
        admin_user_a: User,
    ):
        """Plan A's admin cannot open the edit view for plan B's root page."""
        client.force_login(admin_user_a)
        response = client.get(f'/admin/pages/{plan_b.root_page.pk}/edit/')
        # Wagtail raises PermissionDenied which the admin decorator turns
        # into a 302 redirect to the admin home.
        assert response.status_code == 302
        assert response.url == '/admin/'

    def test_editing_other_plans_child_page_is_denied(
        self,
        client,
        plan_b_child_page: Page,
        admin_user_a: User,
    ):
        """Plan A's admin cannot open the edit view for a plan B child page."""
        client.force_login(admin_user_a)
        response = client.get(f'/admin/pages/{plan_b_child_page.pk}/edit/')
        assert response.status_code == 302
        assert response.url == '/admin/'

    def test_own_plan_edit_still_works(
        self,
        client,
        plan_a_child_page: Page,
        admin_user_a: User,
    ):
        """Sanity check: plan A's admin *can* edit their own plan's pages."""
        client.force_login(admin_user_a)
        response = client.get(f'/admin/pages/{plan_a_child_page.pk}/edit/')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests - _wagtail_site effect on Wagtail internals
# ---------------------------------------------------------------------------


def _request_with_site(site):
    """Create a GET request with ``_wagtail_site`` pre-set."""
    request = RequestFactory().get('/')
    request._wagtail_site = site  # type: ignore[attr-defined]
    return request


@pytest.fixture
def _only_plan_sites(plan_a: Plan, plan_b: Plan):
    """Delete any Wagtail sites not belonging to the two test plans."""
    from wagtail.models import Site

    Site.objects.exclude(pk__in=[plan_a.site_id, plan_b.site_id]).delete()
    Site.clear_site_root_paths_cache()


@pytest.mark.usefixtures('_only_plan_sites')
class TestWagtailSiteEffect:
    """
    Verify how ``_wagtail_site`` influences Wagtail URL resolution and routing.

    The reason for this is that our admin middleware is short-circuiting
    Wagtail's site resolving code by injecting that attribute to the request.
    We need to verify that Wagtail keeps using that internal attribute.

    ``AplansPage.get_url_parts`` short-circuits the base Wagtail
    implementation, making URL parts plan-intrinsic.  ``Page.get_url``
    and ``Page.route_for_request`` still consult ``_wagtail_site`` via
    ``Site.find_for_request``.
    """

    # -- Code path 1: AplansPage.get_url_parts --

    def test_get_url_parts_returns_own_plan_regardless_of_wagtail_site(
        self,
        plan_a: Plan,
        plan_b: Plan,
        plan_a_child_page: Page,
    ):
        """``get_url_parts`` returns the page's own plan site regardless of ``_wagtail_site``."""
        request = _request_with_site(plan_b.site)
        url_parts = plan_a_child_page.specific.get_url_parts(request=request)
        assert url_parts is not None
        site_id, root_url, _page_path = url_parts
        assert site_id == plan_a.site_id
        assert root_url == f'https://{plan_a.default_hostname()}'

    # -- Code path 2: Page.get_url relative vs full URL --

    def test_get_url_returns_relative_path_when_wagtail_site_matches(
        self,
        plan_a: Plan,
        plan_a_child_page: Page,
    ):
        """``get_url`` returns a relative path when ``_wagtail_site`` matches."""
        request = _request_with_site(plan_a.site)
        url = plan_a_child_page.specific.get_url(request=request)
        assert url is not None
        assert url == plan_a_child_page.url_path
        assert url.startswith('/')
        assert '://' not in url

    def test_get_url_returns_full_url_when_wagtail_site_differs(
        self,
        plan_a: Plan,
        plan_b: Plan,
        plan_a_child_page: Page,
    ):
        """``get_url`` returns a full URL when ``_wagtail_site`` belongs to another plan."""
        request = _request_with_site(plan_b.site)
        url = plan_a_child_page.specific.get_url(request=request)
        assert url is not None
        assert url.startswith(f'https://{plan_a.default_hostname()}')

    def test_get_url_returns_full_url_when_no_wagtail_site(
        self,
        plan_a: Plan,
        plan_a_child_page: Page,
    ):
        """``get_url`` returns a full URL when no ``_wagtail_site`` is set."""
        request = RequestFactory().get('/')
        url = plan_a_child_page.specific.get_url(request=request)
        assert url is not None
        assert url.startswith(f'https://{plan_a.default_hostname()}')

    # -- Code path 3: Page.route_for_request --

    def test_route_for_request_finds_page_under_wagtail_site(
        self,
        plan_a: Plan,
        plan_a_child_page: Page,
    ):
        """``route_for_request`` finds a page under the ``_wagtail_site`` tree."""
        request = _request_with_site(plan_a.site)
        result = Page.route_for_request(request, plan_a_child_page.slug + '/')
        assert result is not None
        assert result.page.pk == plan_a_child_page.pk

    def test_route_for_request_cannot_find_other_sites_page(
        self,
        plan_a: Plan,
        plan_b_child_page: Page,
    ):
        """``route_for_request`` returns ``None`` for a page in another site tree."""
        request = _request_with_site(plan_a.site)
        result = Page.route_for_request(request, plan_b_child_page.slug + '/')
        assert result is None

    def test_route_for_request_returns_none_without_wagtail_site(
        self,
    ):
        """``route_for_request`` returns ``None`` without ``_wagtail_site`` or matching host."""
        request = RequestFactory().get('/')
        result = Page.route_for_request(request, 'any/')
        assert result is None

    def test_route_for_request_caches_result(
        self,
        plan_a: Plan,
        plan_a_child_page: Page,
    ):
        """``route_for_request`` caches its result on the request object."""
        request = _request_with_site(plan_a.site)
        first = Page.route_for_request(request, plan_a_child_page.slug + '/')
        assert hasattr(request, '_wagtail_route_for_request')
        second = Page.route_for_request(request, plan_a_child_page.slug + '/')
        assert first is second
