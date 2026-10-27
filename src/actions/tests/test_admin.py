from __future__ import annotations

import typing
from datetime import timedelta
from unittest.mock import Mock

from django.contrib.admin.utils import quote
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Locale

import pytest
from pytest_django.asserts import assertContains, assertNotContains

from actions.action_admin import ActionAdmin
from actions.attribute_type_admin import AttributeTypeAdmin
from actions.models import AttributeType, CategoryType
from actions.pledge_admin import PledgeIndexView, PledgeViewSet
from actions.tests.factories import (
    ActionFactory,
    AttributeTypeFactory,
    CategoryTypeFactory,
    PlanDomainFactory,
    PlanFactory,
    PledgeFactory,
)
from actions.tests.utils import instantiate_view
from actions.wagtail_admin import PlanIndexView, PlanViewSet
from admin_site.tests.factories import ClientPlanFactory

if typing.TYPE_CHECKING:
    from aplans.pytest_fixtures import ModelAdminEditTest

    from actions.models import Action
    from people.models import Person
    from users.models import User

pytestmark = pytest.mark.django_db


def get_request(rf, user=None, view_name='wagtailadmin_home', url=None):
    if url is None:
        url = reverse(view_name)
    request = rf.get(url)
    if user is not None:
        request.user = user
    return request


def get_plan_index_view(rf, client, user, view_set=None) -> PlanIndexView:
    if view_set is None:
        view_set = PlanViewSet()
    client.force_login(user)
    request = get_request(rf, user)
    index_view = instantiate_view(view_set.index_view, PlanIndexView)
    index_view.setup(request)
    return index_view


def get_pledge_index_view(rf, user, view_set=None) -> PledgeIndexView:
    if view_set is None:
        view_set = PledgeViewSet()
    request = get_request(rf, user)
    index_view = instantiate_view(view_set.index_view, PledgeIndexView)
    index_view.setup(request)
    return index_view


def edit_button_shown(rf, client, user, plan) -> bool:
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, user, view_set)
    buttons = index_view.get_list_buttons(user.get_active_admin_plan())
    edit_url_name = view_set.get_url_name('edit')
    return any(
        any(b.url == reverse(edit_url_name, args=[plan.pk]) for b in getattr(button, 'dropdown_buttons', []))
        for button in buttons
    )


@pytest.mark.parametrize('user__is_staff', [False])
def test_no_access_for_non_staff_user(user, client):
    client.force_login(user)
    response = client.get(reverse('wagtailadmin_home'), follow=True)
    assertContains(response, 'You do not have permission to access the admin')


def test_login_removes_user_from_staff_if_no_plan_admin(user, client):
    assert user.is_staff
    assert not user.get_adminable_plans()
    client.force_login(user)
    user.refresh_from_db()
    assert not user.is_staff


def test_plan_edit_button_shown_to_superuser(rf, client, superuser, plan):
    assert edit_button_shown(rf, client, superuser, plan)


def test_plan_edit_button_shown_to_plan_admin(rf, client, plan_admin_user, plan):
    assert edit_button_shown(rf, client, plan_admin_user, plan)


def test_plan_edit_button_not_shown_to_action_contact_person(rf, client, action_contact_person_user, plan):
    assert not edit_button_shown(rf, client, action_contact_person_user, plan)


def test_pledge_translate_listing_button_hidden(rf, superuser, plan):
    plan.features.enable_community_engagement = True
    plan.features.save()
    Locale.objects.get_or_create(language_code='fi')
    pledge = PledgeFactory.create(plan=plan)

    view_set = PledgeViewSet()
    index_view = get_pledge_index_view(rf, superuser, view_set)
    list_buttons = index_view.get_list_buttons(pledge)

    dropdown_urls = [b.url for button in list_buttons for b in getattr(button, 'dropdown_buttons', [])]
    translate_url = reverse(
        'wagtail_localize:submit_snippet_translation',
        args=[pledge._meta.app_label, pledge._meta.model_name, quote(pledge.pk)],
    )
    assert translate_url not in dropdown_urls


def test_superuser_can_list_plans(rf, superuser, plan, client):
    other_plan = PlanFactory.create()
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, superuser, view_set)
    qs = index_view.get_queryset()
    assert plan in qs
    assert other_plan in qs


def test_plan_listing_shows_identifier_with_copy_button(superuser, client):
    PlanFactory.create(identifier='my-unique-plan-id')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    # The identifier is shown in the listing, together with a click-to-copy button.
    assertContains(response, 'my-unique-plan-id')
    assertContains(response, 'data-copy-identifier="my-unique-plan-id"')


def test_plan_listing_is_horizontally_scrollable_with_pinned_columns(superuser, client):
    PlanFactory.create()
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    # The listing table is wrapped in the reusable scrollable container, and the leftmost
    # columns are tagged as pinned so they stay visible while the rest scroll.
    assertContains(response, 'kw-scroll-table')
    assertContains(response, 'kw-col--pin')
    # Plans opts into viewport fill, so the container gets the --fill modifier.
    assertContains(response, 'kw-scroll-table--fill')
    # Site status is the final pinned column (the pin/scroll boundary).
    assertContains(response, 'kw-col--pin-last')


def test_plan_listing_results_fragment_keeps_scroll_wrapper(superuser, client):
    # Wagtail swaps #listing-results via AJAX (filter/search). That results fragment must also
    # carry the scroll wrapper, or the horizontal scroll disappears after the first swap.
    PlanFactory.create()
    results_url = reverse(PlanViewSet().get_url_name('list_results'))
    client.force_login(superuser)
    response = client.get(results_url)
    assert response.status_code == 200
    assertContains(response, 'kw-scroll-table')


def test_inactive_plan_hidden_by_default_but_flagged_when_shown(superuser, client):
    # A unique identifier, so we can look for this plan's row (its copy button) specifically,
    # rather than its name, which also appears in the admin chrome.
    PlanFactory.create(is_active=False, identifier='uniq-inactive-plan')
    row_marker = 'data-copy-identifier="uniq-inactive-plan"'
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    # By default the listing filters to active plans, so the inactive one's row is not shown.
    default_response = client.get(index_url)
    assert default_response.status_code == 200
    assertNotContains(default_response, row_marker)

    # When inactive plans are included (via the Active status filter), the row is flagged with
    # the inactive state class and the warning icon.
    response = client.get(index_url, {'is_active': 'inactive'})
    assert response.status_code == 200
    assertContains(response, row_marker)
    assertContains(response, 'is-inactive')
    assertContains(response, 'icon-warning')


def test_internal_plan_flagged_with_key_icon_not_site_status_text(superuser, client):
    PlanFactory.create(
        visibility='internal',
        identifier='uniq-internal-plan',
    )
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    assertContains(response, 'data-copy-identifier="uniq-internal-plan"')
    # Internal plans are flagged with a key icon next to the Site status badge...
    assertContains(response, 'plan-status-internal')
    # ...no longer in the left plan-flags column...
    assertNotContains(response, 'plan-flag--internal')
    # ...and no longer with an "Internal" text badge in the Site status column.
    assertNotContains(response, '<span class="w-status">Internal</span>')


def test_public_plan_not_flagged_internal(superuser, client):
    PlanFactory.create(visibility='public', identifier='uniq-public-plan')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    assertContains(response, 'data-copy-identifier="uniq-public-plan"')
    assertNotContains(response, 'plan-flag--internal')


def _marker(identifier: str) -> str:
    return f'data-copy-identifier="{identifier}"'


def test_site_status_filter_narrows_to_the_chosen_live_state(superuser, client):
    now = timezone.now()
    live = PlanFactory.create(identifier='uniq-live', published_at=now - timedelta(days=1))
    scheduled = PlanFactory.create(identifier='uniq-scheduled', published_at=now + timedelta(days=1))
    not_live = PlanFactory.create(identifier='uniq-not-live', published_at=None)
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url, {'live_state': 'live'})
    assert response.status_code == 200
    assertContains(response, _marker(live.identifier))
    assertNotContains(response, _marker(scheduled.identifier))
    assertNotContains(response, _marker(not_live.identifier))

    response = client.get(index_url, {'live_state': 'scheduled'})
    assertContains(response, _marker(scheduled.identifier))
    assertNotContains(response, _marker(live.identifier))
    assertNotContains(response, _marker(not_live.identifier))

    response = client.get(index_url, {'live_state': 'not_live'})
    assertContains(response, _marker(not_live.identifier))
    assertNotContains(response, _marker(live.identifier))
    assertNotContains(response, _marker(scheduled.identifier))


def test_usage_status_filter_narrows_to_the_chosen_usage(superuser, client):
    sales = PlanFactory.create(identifier='uniq-sales', usage_status='sales')
    customer = PlanFactory.create(identifier='uniq-customer', usage_status='customer_use')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url, {'usage_status': 'sales'})
    assert response.status_code == 200
    assertContains(response, _marker(sales.identifier))
    assertNotContains(response, _marker(customer.identifier))


def test_usage_status_filter_is_superuser_only(plan_admin_user, client):
    # Non-superusers never see the usage column, so they must not get its filter either.
    from actions.wagtail_admin import PlanFilter

    plan_filter = PlanFilter(request=Mock(user=plan_admin_user))
    assert 'usage_status' not in plan_filter.filters


def test_organization_filter_narrows_to_the_chosen_organization(superuser, client):
    wanted = PlanFactory.create(identifier='uniq-org-wanted')
    other = PlanFactory.create(identifier='uniq-org-other')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url, {'organization': wanted.organization_id})
    assert response.status_code == 200
    assertContains(response, _marker(wanted.identifier))
    assertNotContains(response, _marker(other.identifier))


def test_parent_filter_narrows_to_children_of_the_chosen_umbrella(superuser, client):
    umbrella = PlanFactory.create(identifier='uniq-umbrella')
    child = PlanFactory.create(identifier='uniq-child', parent=umbrella)
    standalone = PlanFactory.create(identifier='uniq-standalone')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url, {'parent': umbrella.id})
    assert response.status_code == 200
    assertContains(response, _marker(child.identifier))
    assertNotContains(response, _marker(standalone.identifier))
    assertNotContains(response, _marker(umbrella.identifier))


def test_currently_active_plan_is_marked(superuser, client):
    active = PlanFactory.create(identifier='uniq-active-plan')
    PlanFactory.create(identifier='uniq-other-plan')
    superuser.selected_admin_plan = active
    superuser.save(update_fields=['selected_admin_plan'])
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    # Exactly one row (the currently active admin plan) carries the active-plan marker.
    assertContains(response, 'is-active-plan', count=1)


def _marker_positions(response, *identifiers):
    html = response.content.decode()
    return [html.index(f'data-copy-identifier="{ident}"') for ident in identifiers]


def _set_created_at(plan, when):
    # created_at is auto_now_add, so set it explicitly with an update() that bypasses it.
    from actions.models import Plan

    Plan.objects.filter(pk=plan.pk).update(created_at=when)


def test_plan_listing_groups_children_under_their_umbrella(superuser, client):
    # Creation times are chosen so the grouping is distinguishable from a plain created-at sort.
    # A family is ranked by the latest creation time of any plan in it: the umbrella's family wins
    # because its newest child is the newest plan overall, even though the umbrella itself is the
    # oldest. Within the family the umbrella comes first, then children newest-first. Expected
    # order: umbrella, child-newer, child-older, standalone.
    now = timezone.now()
    umbrella = PlanFactory.create(name='Umbrella', identifier='grp-umbrella')
    child_newer = PlanFactory.create(name='Child newer', identifier='grp-child-new', parent=umbrella)
    child_older = PlanFactory.create(name='Child older', identifier='grp-child-old', parent=umbrella)
    standalone = PlanFactory.create(name='Standalone', identifier='grp-standalone')
    _set_created_at(umbrella, now - timedelta(days=4))
    _set_created_at(child_older, now - timedelta(days=3))
    _set_created_at(standalone, now - timedelta(days=2))
    _set_created_at(child_newer, now - timedelta(days=1))

    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200

    umb, new_child, old_child, alone = _marker_positions(
        response, 'grp-umbrella', 'grp-child-new', 'grp-child-old', 'grp-standalone',
    )
    # The family block is contiguous and ranked above the standalone (its newest child is newest
    # overall); the umbrella leads, then children newest-first.
    assert umb < new_child < old_child < alone


def test_plan_listing_explicit_sort_bypasses_family_grouping(superuser, client):
    umbrella = PlanFactory.create(name='M umbrella', identifier='grp-umbrella')
    PlanFactory.create(name='A child', identifier='grp-child-a', parent=umbrella)
    PlanFactory.create(name='B child', identifier='grp-child-b', parent=umbrella)
    PlanFactory.create(name='A standalone', identifier='grp-standalone')

    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    # An explicit column sort opts out of grouping: by name the rows go a-child, a-standalone,
    # b-child, m-umbrella -> the standalone falls *between* the two children, which family
    # grouping would never allow.
    response = client.get(index_url, {'ordering': 'name'})
    assert response.status_code == 200

    child_a, standalone, child_b = _marker_positions(
        response, 'grp-child-a', 'grp-standalone', 'grp-child-b',
    )
    assert child_a < standalone < child_b


def test_child_plan_row_is_marked_as_child(superuser, client):
    # Only the child row carries the child marker; the umbrella and an unrelated standalone do not.
    umbrella = PlanFactory.create(name='Umbrella', identifier='ind-umbrella')
    PlanFactory.create(name='Child', identifier='ind-child', parent=umbrella)
    PlanFactory.create(name='Standalone', identifier='ind-standalone')

    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    assertContains(response, 'plan-title--child', count=1)
    # No explicit sort, so no sort banner.
    assertNotContains(response, 'plan-sort-active')


def test_explicit_sort_hides_child_markers_and_shows_clear_sort(superuser, client):
    umbrella = PlanFactory.create(name='Umbrella', identifier='srt-umbrella')
    PlanFactory.create(name='Child', identifier='srt-child', parent=umbrella)

    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url, {'ordering': 'name'})
    assert response.status_code == 200
    # Grouping is off under an explicit sort, so the child indent/arrow is gone...
    assertNotContains(response, 'plan-title--child')
    # ...and a sort banner offers a link back to the grouped (un-ordered) default.
    assertContains(response, 'plan-sort-active')
    assertContains(response, 'plan-sort-clear')
    assertContains(response, f'href="{index_url}"')


def test_child_without_its_umbrella_in_view_is_not_indented(superuser, client):
    # When a filter matches a child but not its umbrella, the umbrella row is absent, so the
    # child must render as a top-level row rather than a dangling indent under nothing. The
    # Parent column still names the umbrella.
    umbrella = PlanFactory.create(name='Umbrella', identifier='orph-umbrella', usage_status='customer_use')
    child = PlanFactory.create(name='Child', identifier='orph-child', parent=umbrella, usage_status='sales')

    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url, {'usage_status': 'sales'})
    assert response.status_code == 200

    # Only the child matches the filter; its umbrella is filtered out.
    assertContains(response, _marker(child.identifier))
    assertNotContains(response, _marker(umbrella.identifier))
    # So the child is not drawn as an indented child of a missing umbrella.
    assertNotContains(response, 'plan-title--child')


def test_child_stays_indented_when_its_umbrella_is_also_in_view(superuser, client):
    # A filter that keeps the whole family intact must leave the child indented under its umbrella.
    umbrella = PlanFactory.create(name='Umbrella', identifier='keep-umbrella', usage_status='sales')
    PlanFactory.create(name='Child', identifier='keep-child', parent=umbrella, usage_status='sales')

    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url, {'usage_status': 'sales'})
    assert response.status_code == 200

    assertContains(response, 'plan-title--child', count=1)


def test_usage_status_column_is_sortable(superuser, client):
    customer = PlanFactory.create(identifier='sort-customer', usage_status='customer_use')
    sales = PlanFactory.create(identifier='sort-sales', usage_status='sales')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    asc = client.get(index_url, {'ordering': 'usage_status'})
    assert asc.status_code == 200
    c_pos, s_pos = _marker_positions(asc, customer.identifier, sales.identifier)
    assert c_pos < s_pos  # 'customer_use' sorts before 'sales'

    desc = client.get(index_url, {'ordering': '-usage_status'})
    c_pos, s_pos = _marker_positions(desc, customer.identifier, sales.identifier)
    assert s_pos < c_pos


def test_site_status_column_is_sortable(superuser, client):
    not_live = PlanFactory.create(identifier='sort-notlive', published_at=None)
    live = PlanFactory.create(identifier='sort-live', published_at=timezone.now() - timedelta(days=1))
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    asc = client.get(index_url, {'ordering': 'live_state'})
    assert asc.status_code == 200
    nl_pos, l_pos = _marker_positions(asc, not_live.identifier, live.identifier)
    assert nl_pos < l_pos  # NOT_LIVE sorts before LIVE

    desc = client.get(index_url, {'ordering': '-live_state'})
    nl_pos, l_pos = _marker_positions(desc, not_live.identifier, live.identifier)
    assert l_pos < nl_pos


@override_settings(HOSTNAME_PLAN_DOMAINS=['watch.test'])
def test_unlaunched_plan_lists_production_then_wildcard_then_preview(superuser, client):
    # An unlaunched plan shows its preview domain too, after the production and wildcard surfaces.
    plan = PlanFactory.create(identifier='dom-plan', published_at=None)
    PlanDomainFactory.create(plan=plan, hostname='preview.example.test', deployment_environment='preview')
    PlanDomainFactory.create(plan=plan, hostname='www.example.test', deployment_environment='production')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url)
    assert response.status_code == 200
    html = response.content.decode()
    sep = html.index('plan-row-menu__separator')
    prod = html.index('https://www.example.test')
    wildcard = html.index('https://dom-plan.watch.test')
    preview = html.index('https://preview.example.test')
    assert sep < prod < wildcard < preview


@override_settings(HOSTNAME_PLAN_DOMAINS=['watch.test'])
def test_live_plan_with_launched_production_domain_shows_only_that_domain(superuser, client):
    # PlanFactory publishes in the past, so the plan (and thus its production domain) is launched.
    # The wildcard host and the preview domain are then secondary noise and are dropped; only the
    # custom production domain is linked.
    plan = PlanFactory.create(identifier='dom-plan')
    PlanDomainFactory.create(plan=plan, hostname='preview.example.test', deployment_environment='preview')
    PlanDomainFactory.create(plan=plan, hostname='www.example.test', deployment_environment='production')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'https://www.example.test' in html
    assert 'https://dom-plan.watch.test' not in html
    assert 'https://preview.example.test' not in html


@override_settings(HOSTNAME_PLAN_DOMAINS=['watch.test'])
def test_live_plan_without_a_custom_production_domain_still_shows_preview(superuser, client):
    # Live, but the only custom domain is a preview one (the wildcard host does not count as a
    # production domain), so the preview link is still shown.
    plan = PlanFactory.create(identifier='dom-plan')
    PlanDomainFactory.create(plan=plan, hostname='preview.example.test', deployment_environment='preview')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'https://dom-plan.watch.test' in html
    assert 'https://preview.example.test' in html


@override_settings(HOSTNAME_PLAN_DOMAINS=['watch.test'])
def test_row_menu_excludes_redirect_only_domains(superuser, client):
    plan = PlanFactory.create(identifier='dom-plan')
    PlanDomainFactory.create(plan=plan, hostname='serving.example.test', deployment_environment='production')
    PlanDomainFactory.create(plan=plan, hostname='old.example.test', redirect_to_hostname='serving.example.test')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'https://serving.example.test' in html
    assert 'old.example.test' not in html


@override_settings(HOSTNAME_PLAN_DOMAINS=['watch.test'])
def test_row_menu_links_the_derived_wildcard_host_without_a_custom_domain(superuser, client):
    # A plan with no custom PlanDomain is still served on the deployment's wildcard host.
    PlanFactory.create(identifier='wild-plan')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'plan-row-menu__separator' in html
    assert 'https://wild-plan.watch.test' in html


@override_settings(HOSTNAME_PLAN_DOMAINS=['localhost'], DEPLOYMENT_TYPE='production')
def test_row_menu_has_no_domain_separator_without_any_serving_url(superuser, client):
    # No custom domain and no wildcard base configured, so there is nothing to link.
    PlanFactory.create(identifier='nodom-plan')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)

    response = client.get(index_url)
    assert response.status_code == 200
    assertNotContains(response, 'plan-row-menu__separator')


def test_plan_listing_clamps_narrow_column_cells(superuser, client):
    # The narrow columns (organization, clients, ...) clamp their text to a few lines with an
    # ellipsis, so a long organization name can't make a row arbitrarily tall.
    PlanFactory.create(identifier='clamp-plan')
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    assertContains(response, 'plan-cell-clamp')


def test_plan_listing_shows_site_status_before_version_name(superuser, client):
    PlanFactory.create()
    index_url = reverse(PlanViewSet().get_url_name('list'))
    client.force_login(superuser)
    response = client.get(index_url)
    assert response.status_code == 200
    # Site status is high priority, so it is reordered to sit right after the name column,
    # ahead of the lower-priority columns such as the version name.
    content = response.content.decode()
    assert content.index('Site status') < content.index('Version name')


def test_admin_can_list_only_own_plan(rf, plan, plan_admin_user, client):
    other_plan = PlanFactory.create()
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, plan_admin_user, view_set)
    qs = index_view.get_queryset()
    assert plan in qs
    assert other_plan not in qs


def test_can_access_plan_edit_page(plan, plan_admin_user, client):
    ClientPlanFactory.create(plan=plan)
    view_set = PlanViewSet()
    edit_url_name = view_set.get_url_name('edit')
    url = reverse(edit_url_name, args=[plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    assert response.status_code == 200


def test_plan_edit_page_has_no_new_organization_field(plan, plan_admin_user, client):
    # The field is only for creating a plan; unclaimed by any panel, Wagtail would render it bare.
    ClientPlanFactory.create(plan=plan)
    url = reverse(PlanViewSet().get_url_name('edit'), args=[plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    assert response.status_code == 200
    assert 'name="organization_name"' not in response.content.decode('utf-8')


def test_cannot_access_other_plan_edit_page(plan, plan_admin_user, client):
    other_plan = PlanFactory.create()
    view_set = PlanViewSet()
    edit_url_name = view_set.get_url_name('edit')
    url = reverse(edit_url_name, args=[other_plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    # Wagtail doesn't respond with HTTP status 403 but with a redirect and an error message in a cookie.
    view_set.permission_policy.user_has_permission_for_instance(plan_admin_user, 'edit', plan)
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')


def test_action_admin(
    plan_admin_user: User,
    action_contact_person: Person,
    action: Action,
    test_modeladmin_edit: ModelAdminEditTest,
):
    ClientPlanFactory(plan=action.plan)
    post_data = dict(name='Modified name', identifier=action.identifier)
    test_modeladmin_edit(
        ActionAdmin,
        action,
        plan_admin_user,
        post_data=post_data,
        can_inspect=True,
        can_edit=True,
    )
    return
    # FIXME
    action.refresh_from_db()
    # assert action.name == post_data['name']
    test_modeladmin_edit(
        ActionAdmin,
        action,
        action_contact_person.user,
        post_data=post_data,
        can_inspect=True,
        can_edit=True,
    )
    other_action = ActionFactory.create(plan=action.plan)
    test_modeladmin_edit(
        ActionAdmin,
        other_action,
        plan_admin_user,
        post_data=post_data,
        can_inspect=True,
        can_edit=True,
    )
    test_modeladmin_edit(
        ActionAdmin,
        other_action,
        action_contact_person.user,
        post_data=post_data,
        can_inspect=True,
        can_edit=False,
    )


class TestAttributeTypeAdminQueryset:
    """Tests for AttributeTypeAdmin.get_queryset filtering based on community engagement feature."""

    @pytest.fixture
    def action_attribute_type(self, plan):
        """Create an attribute type for actions scoped to the plan."""
        action_ct = ContentType.objects.get(app_label='actions', model='action')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        return AttributeTypeFactory.create(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            name='Action Attribute',
        )

    @pytest.fixture
    def category_attribute_type(self, plan):
        """Create an attribute type for categories scoped to a category type."""
        category_ct = ContentType.objects.get(app_label='actions', model='category')
        category_type_ct = ContentType.objects.get(app_label='actions', model='categorytype')
        category_type = CategoryTypeFactory.create(plan=plan)
        return AttributeTypeFactory.create(
            object_content_type=category_ct,
            scope_content_type=category_type_ct,
            scope_id=category_type.id,
            name='Category Attribute',
        )

    @pytest.fixture
    def pledge_attribute_type(self, plan):
        """Create an attribute type for pledges scoped to the plan."""
        pledge_ct = ContentType.objects.get(app_label='actions', model='pledge')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        return AttributeTypeFactory.create(
            object_content_type=pledge_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            name='Pledge Attribute',
        )

    def test_pledge_attribute_types_excluded_when_community_engagement_disabled(
        self,
        rf,
        plan,
        plan_admin_user,
        action_attribute_type,
        category_attribute_type,
        pledge_attribute_type,
    ):
        """Pledge attribute types should not appear when community engagement is disabled."""
        plan.features.enable_community_engagement = False
        plan.features.save()

        admin = AttributeTypeAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        qs = admin.get_queryset(request)

        assert action_attribute_type in qs
        assert category_attribute_type in qs
        assert pledge_attribute_type not in qs

    def test_pledge_attribute_types_included_when_community_engagement_enabled(
        self,
        rf,
        plan,
        plan_admin_user,
        action_attribute_type,
        category_attribute_type,
        pledge_attribute_type,
    ):
        """Pledge attribute types should appear when community engagement is enabled."""
        plan.features.enable_community_engagement = True
        plan.features.save()

        admin = AttributeTypeAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        qs = admin.get_queryset(request)

        assert action_attribute_type in qs
        assert category_attribute_type in qs
        assert pledge_attribute_type in qs


class TestAttributeTypeAdminButtonHelper:
    """Tests for AttributeTypeAdminButtonHelper preserving content_type parameter."""

    @pytest.fixture
    def attribute_type(self, plan):
        """Create an attribute type for testing."""
        action_ct = ContentType.objects.get(app_label='actions', model='action')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        return AttributeTypeFactory.create(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            name='Test Attribute',
        )

    def test_add_button_shown_with_content_type_parameter(self, rf, plan, plan_admin_user, attribute_type):
        """Add button should be shown when content_type parameter is present."""
        from actions.attribute_type_admin import AttributeTypeAdmin, AttributeTypeAdminButtonHelper

        admin = AttributeTypeAdmin()
        request = rf.get(f'/admin/?content_type={attribute_type.object_content_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.url_helper.create_url = '/admin/create/'
        view.permission_helper = Mock()

        helper = AttributeTypeAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is not None
        assert f'content_type={attribute_type.object_content_type.id}' in result['url']

    def test_add_button_hidden_without_content_type_parameter(self, rf, plan, plan_admin_user):
        """Add button should be hidden when content_type parameter is missing."""
        from actions.attribute_type_admin import AttributeTypeAdmin, AttributeTypeAdminButtonHelper

        admin = AttributeTypeAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.permission_helper = Mock()

        helper = AttributeTypeAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is None

    def test_edit_button_preserves_content_type_parameter(self, rf, plan, plan_admin_user, attribute_type):
        """Edit button should preserve content_type parameter in URL."""
        from actions.attribute_type_admin import AttributeTypeAdminButtonHelper

        request = rf.get(f'/admin/?content_type={attribute_type.object_content_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = AttributeType._meta.model
        view.url_helper = Mock()
        view.url_helper.get_action_url = Mock(side_effect=lambda action, pk: f'/admin/{action}/{pk}/')
        view.permission_helper = Mock()

        helper = AttributeTypeAdminButtonHelper(view, request)
        result = helper.edit_button(pk=attribute_type.id)

        assert result is not None
        assert f'content_type={attribute_type.object_content_type.id}' in result['url']


class TestCategoryAdminButtonHelper:
    """Tests for CategoryAdminButtonHelper preserving category_type parameter."""

    @pytest.fixture
    def category_type(self, plan):
        """Create a category type for testing."""
        return CategoryTypeFactory.create(plan=plan, name='Test Category Type')

    def test_add_button_shown_with_category_type_parameter(self, rf, plan, plan_admin_user, category_type):
        """Add button should be shown when category_type parameter is present."""
        from actions.category_admin import CategoryAdmin, CategoryAdminButtonHelper

        admin = CategoryAdmin()
        request = rf.get(f'/admin/?category_type={category_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.url_helper.create_url = '/admin/create/'
        view.permission_helper = Mock()

        helper = CategoryAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is not None
        assert f'category_type={category_type.id}' in result['url']

    def test_add_button_hidden_without_category_type_parameter(self, rf, plan, plan_admin_user):
        """Add button should be hidden when category_type parameter is missing."""
        from actions.category_admin import CategoryAdmin, CategoryAdminButtonHelper

        admin = CategoryAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.permission_helper = Mock()

        helper = CategoryAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is None

    def test_inspect_button_preserves_category_type_parameter(self, rf, plan, plan_admin_user, category_type):
        """Inspect button should preserve category_type parameter in URL."""
        from actions.category_admin import CategoryAdminButtonHelper

        request = rf.get(f'/admin/?category_type={category_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = CategoryType._meta.model
        view.url_helper = Mock()
        view.url_helper.get_action_url = Mock(side_effect=lambda action, pk: f'/admin/{action}/{pk}/')
        view.permission_helper = Mock()

        helper = CategoryAdminButtonHelper(view, request)
        result = helper.inspect_button(pk=category_type.id)

        assert result is not None
        assert f'category_type={category_type.id}' in result['url']


def test_action_responsible_party_swap_should_succeed(plan_admin_user, action, client):
    """
    Test that swapping organizations between ActionResponsibleParty instances works correctly.

    When swapping organizations between different roles (e.g., org A moves from primary
    to collaborator, org B moves from collaborator to primary), the final state has
    each organization appearing only once, so this should be a valid operation.

    """
    from actions.action_admin import ActionAdmin
    from actions.models import ActionResponsibleParty
    from actions.tests.factories import ActionResponsiblePartyFactory
    from admin_site.tests.factories import ClientPlanFactory
    from orgs.tests.factories import OrganizationFactory

    # Setup: Create the plan's client association
    ClientPlanFactory.create(plan=action.plan)

    # Create two organizations
    org_a = OrganizationFactory.create()
    org_b = OrganizationFactory.create()

    # Create two ActionResponsibleParty records with different organizations and roles
    # Initial state: org_a is PRIMARY, org_b is COLLABORATOR
    arp_primary = ActionResponsiblePartyFactory.create(
        action=action,
        organization=org_a,
        role=ActionResponsibleParty.Role.PRIMARY,
    )
    arp_collaborator = ActionResponsiblePartyFactory.create(
        action=action,
        organization=org_b,
        role=ActionResponsibleParty.Role.COLLABORATOR,
    )

    # Get the edit URL for the action
    admin = ActionAdmin()
    edit_url_name = admin.url_helper.get_action_url_name('edit')
    edit_url = reverse(edit_url_name, kwargs={'instance_pk': action.pk})

    # Login as plan admin
    client.force_login(plan_admin_user)

    # Construct POST data that swaps the organizations between the two roles
    # Desired state: org_b is PRIMARY, org_a is COLLABORATOR
    post_data = {
        # Required action fields
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',  # Required field
        # Primary responsible parties formset - swap to org B
        'responsible_parties_primary-TOTAL_FORMS': '1',
        'responsible_parties_primary-INITIAL_FORMS': '1',
        'responsible_parties_primary-MIN_NUM_FORMS': '0',
        'responsible_parties_primary-MAX_NUM_FORMS': '1000',
        'responsible_parties_primary-0-id': arp_primary.pk,
        'responsible_parties_primary-0-organization': org_b.pk,  # Swapped from org_a
        'responsible_parties_primary-0-ORDER': '1',
        # Collaborator responsible parties formset - swap to org A
        'responsible_parties_collaborator-TOTAL_FORMS': '1',
        'responsible_parties_collaborator-INITIAL_FORMS': '1',
        'responsible_parties_collaborator-MIN_NUM_FORMS': '0',
        'responsible_parties_collaborator-MAX_NUM_FORMS': '1000',
        'responsible_parties_collaborator-0-id': arp_collaborator.pk,
        'responsible_parties_collaborator-0-organization': org_a.pk,  # Swapped from org_b
        'responsible_parties_collaborator-0-ORDER': '1',
        # Empty formsets for other relations (required for form validation)
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
    }

    # Execute the POST request - this should succeed with a redirect
    response = client.post(edit_url, data=post_data)

    # Verify successful save (redirect to the action list or detail page)
    assert response.status_code == 302, f'Expected redirect, got {response.status_code}'

    # Query for the responsible parties after the swap
    # Note: The delete-recreate approach means the old PKs no longer exist,
    # so we need to query by organization
    responsible_parties = ActionResponsibleParty.objects.filter(action=action)
    assert responsible_parties.count() == 2, 'Should have exactly 2 responsible parties'

    # Find the parties by organization
    party_with_org_a = responsible_parties.get(organization=org_a)
    party_with_org_b = responsible_parties.get(organization=org_b)

    # Verify the organizations have been swapped to the correct roles
    assert party_with_org_b.role == ActionResponsibleParty.Role.PRIMARY, (
        f'org_b should now be PRIMARY, but has role {party_with_org_b.role}'
    )

    assert party_with_org_a.role == ActionResponsibleParty.Role.COLLABORATOR, (
        f'org_a should now be COLLABORATOR, but has role {party_with_org_a.role}'
    )


def test_action_responsible_party_swap_on_publish_draft(plan):
    """
    Test that publishing a Wagtail draft revision with swapped responsible parties succeeds.

    This tests the code path where Wagtail deserializes a revision (via revision.as_object())
    and then saves it (via Action.publish()). The deserialized action will have child objects
    with existing PKs but swapped organizations, which would cause an IntegrityError without
    the fix in Action._renormalize_revision_items().
    """
    from actions.models import ActionResponsibleParty
    from actions.tests.factories import ActionFactory
    from orgs.tests.factories import OrganizationFactory

    # Create two organizations
    org_a = OrganizationFactory.create()
    org_b = OrganizationFactory.create()

    # Create an action with two responsible parties in initial state
    action = ActionFactory.create(plan=plan)
    ActionResponsibleParty.objects.create(
        action=action,
        organization=org_a,
        role=ActionResponsibleParty.Role.PRIMARY,
        order=0,
    )
    ActionResponsibleParty.objects.create(
        action=action,
        organization=org_b,
        role=ActionResponsibleParty.Role.COLLABORATOR,
        order=1,
    )

    # Create an initial revision (don't publish yet - we'll test publishing the swapped one)
    initial_revision = action.save_revision()

    # Now manually create a revision with swapped responsible parties
    # Get the revision content and modify it to have the swap
    # Note: Use initial_revision.content (dict) not content_json (string)
    revision_content = initial_revision.content.copy()

    # Ensure attributes key exists (required by Action.publish())
    # This is needed because Action.publish() expects it
    if 'attributes' not in revision_content:
        revision_content['attributes'] = {}

    # Find the responsible_parties in the revision content
    # The structure is: revision_content['responsible_parties'] = [list of dicts]
    # Each dict has keys: 'pk', 'order', 'action', 'organization', 'role', 'specifier'
    responsible_parties = revision_content.get('responsible_parties', [])

    # Swap the organizations while keeping the PKs
    for rp in responsible_parties:
        if rp.get('organization') == org_a.pk:
            # This was org_a (PRIMARY), swap to org_b
            rp['organization'] = org_b.pk
        elif rp.get('organization') == org_b.pk:
            # This was org_b (COLLABORATOR), swap to org_a
            rp['organization'] = org_a.pk

    # Create a new revision with the swapped content
    from wagtail.models import Revision

    swapped_revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    swapped_revision.content = revision_content
    swapped_revision.save()

    # Verify current published state is still the original (before swap)
    action.refresh_from_db()
    parties_before = ActionResponsibleParty.objects.filter(action=action)
    assert parties_before.count() == 2
    assert parties_before.get(organization=org_a).role == ActionResponsibleParty.Role.PRIMARY
    assert parties_before.get(organization=org_b).role == ActionResponsibleParty.Role.COLLABORATOR

    # Now publish the revision with swapped responsible parties
    # This should NOT raise IntegrityError
    swapped_revision.publish()

    # Verify the swap was applied successfully
    action.refresh_from_db()
    parties_after = ActionResponsibleParty.objects.filter(action=action)
    assert parties_after.count() == 2

    party_a_after = parties_after.get(organization=org_a)
    party_b_after = parties_after.get(organization=org_b)

    # Verify the organizations have been swapped to the correct roles
    assert party_b_after.role == ActionResponsibleParty.Role.PRIMARY
    assert party_a_after.role == ActionResponsibleParty.Role.COLLABORATOR


def test_action_contact_person_swap_should_succeed(plan_admin_user, action, client):
    """
    Test that swapping persons between ActionContactPerson instances works correctly.

    When swapping persons between different roles (e.g., person A moves from editor
    to moderator, person B moves from moderator to editor), the final state has
    each person appearing only once, so this should be a valid operation.

    This tests the renormalization logic in ActionAdminForm._renormalize_pks_for_swaps().
    """
    from actions.action_admin import ActionAdmin
    from actions.models import ActionContactPerson
    from actions.tests.factories import ActionContactFactory
    from admin_site.tests.factories import ClientPlanFactory
    from people.tests.factories import PersonFactory

    # Setup: Create the plan's client association
    ClientPlanFactory.create(plan=action.plan)

    # Create two persons
    person_a = PersonFactory.create()
    person_b = PersonFactory.create()

    # Create two ActionContactPerson records with different persons and roles
    # Initial state: person_a is EDITOR, person_b is MODERATOR
    acp_editor = ActionContactFactory.create(
        action=action,
        person=person_a,
        role=ActionContactPerson.Role.EDITOR,
    )
    acp_moderator = ActionContactFactory.create(
        action=action,
        person=person_b,
        role=ActionContactPerson.Role.MODERATOR,
    )

    # Get the edit URL for the action
    admin = ActionAdmin()
    edit_url_name = admin.url_helper.get_action_url_name('edit')
    edit_url = reverse(edit_url_name, kwargs={'instance_pk': action.pk})

    # Login as plan admin
    client.force_login(plan_admin_user)

    # Construct POST data that swaps the persons between the two roles
    # Desired state: person_b is EDITOR, person_a is MODERATOR
    post_data = {
        # Required action fields
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',  # Required field
        # Editor contact persons formset - swap to person B
        'contact_persons_editor-TOTAL_FORMS': '1',
        'contact_persons_editor-INITIAL_FORMS': '1',
        'contact_persons_editor-MIN_NUM_FORMS': '0',
        'contact_persons_editor-MAX_NUM_FORMS': '1000',
        'contact_persons_editor-0-id': acp_editor.pk,
        'contact_persons_editor-0-person': person_b.pk,  # Swapped from person_a
        'contact_persons_editor-0-ORDER': '1',
        # Moderator contact persons formset - swap to person A
        'contact_persons_moderator-TOTAL_FORMS': '1',
        'contact_persons_moderator-INITIAL_FORMS': '1',
        'contact_persons_moderator-MIN_NUM_FORMS': '0',
        'contact_persons_moderator-MAX_NUM_FORMS': '1000',
        'contact_persons_moderator-0-id': acp_moderator.pk,
        'contact_persons_moderator-0-person': person_a.pk,  # Swapped from person_b
        'contact_persons_moderator-0-ORDER': '1',
        # Empty formsets for other relations (required for form validation)
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
    }

    # Execute the POST request - this should succeed with a redirect
    response = client.post(edit_url, data=post_data)

    # Verify successful save (redirect to the action list or detail page)
    assert response.status_code == 302, f'Expected redirect, got {response.status_code}'

    # Query for the contact persons after the swap
    contact_persons = ActionContactPerson.objects.filter(action=action)
    assert contact_persons.count() == 2, 'Should have exactly 2 contact persons'

    # Find the contacts by person
    contact_with_person_a = contact_persons.get(person=person_a)
    contact_with_person_b = contact_persons.get(person=person_b)

    # Verify the persons have been swapped to the correct roles
    assert contact_with_person_b.role == ActionContactPerson.Role.EDITOR, (
        f'person_b should now be EDITOR, but has role {contact_with_person_b.role}'
    )

    assert contact_with_person_a.role == ActionContactPerson.Role.MODERATOR, (
        f'person_a should now be MODERATOR, but has role {contact_with_person_a.role}'
    )


def test_action_contact_person_swap_on_publish_draft(plan):
    """
    Test that publishing a Wagtail draft revision with swapped contact persons succeeds.

    This tests the code path where Wagtail deserializes a revision (via revision.as_object())
    and then publishes it (via Action.publish()). The deserialized action will have child objects
    with existing PKs but swapped persons, which would cause an IntegrityError without
    the fix in Action._renormalize_revision_items().
    """
    from actions.models import ActionContactPerson
    from actions.tests.factories import ActionFactory
    from people.tests.factories import PersonFactory

    # Create two persons
    person_a = PersonFactory.create()
    person_b = PersonFactory.create()

    # Create an action with two contact persons in initial state
    action = ActionFactory.create(plan=plan)
    ActionContactPerson.objects.create(
        action=action,
        person=person_a,
        role=ActionContactPerson.Role.EDITOR,
        order=0,
    )
    ActionContactPerson.objects.create(
        action=action,
        person=person_b,
        role=ActionContactPerson.Role.MODERATOR,
        order=1,
    )

    # Create an initial revision (don't publish yet - we'll test publishing the swapped one)
    initial_revision = action.save_revision()

    # Now manually create a revision with swapped contact persons
    # Get the revision content and modify it to have the swap
    revision_content = initial_revision.content.copy()

    # Ensure attributes key exists (required by Action.publish())
    if 'attributes' not in revision_content:
        revision_content['attributes'] = {}

    # Find the contact_persons in the revision content
    # The structure is: revision_content['contact_persons'] = [list of dicts]
    # Each dict has keys: 'pk', 'order', 'action', 'person', 'role', 'primary_contact'
    contact_persons = revision_content.get('contact_persons', [])

    # Swap the persons while keeping the PKs
    for cp in contact_persons:
        if cp.get('person') == person_a.pk:
            # This was person_a (EDITOR), swap to person_b
            cp['person'] = person_b.pk
        elif cp.get('person') == person_b.pk:
            # This was person_b (MODERATOR), swap to person_a
            cp['person'] = person_a.pk

    # Create a new revision with the swapped content
    from wagtail.models import Revision

    swapped_revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    swapped_revision.content = revision_content
    swapped_revision.save()

    # Verify current published state is still the original (before swap)
    action.refresh_from_db()
    contacts_before = ActionContactPerson.objects.filter(action=action)
    assert contacts_before.count() == 2
    assert contacts_before.get(person=person_a).role == ActionContactPerson.Role.EDITOR
    assert contacts_before.get(person=person_b).role == ActionContactPerson.Role.MODERATOR

    # Now publish the revision with swapped contact persons
    # This should NOT raise IntegrityError
    swapped_revision.publish()

    # Verify the swap was applied successfully
    action.refresh_from_db()
    contacts_after = ActionContactPerson.objects.filter(action=action)
    assert contacts_after.count() == 2

    contact_a_after = contacts_after.get(person=person_a)
    contact_b_after = contacts_after.get(person=person_b)

    # Verify the persons have been swapped to the correct roles
    assert contact_b_after.role == ActionContactPerson.Role.EDITOR
    assert contact_a_after.role == ActionContactPerson.Role.MODERATOR


def test_publish_with_new_contact_person_already_in_live_db(plan):
    """
    Publishing must not violate the unique (action, person) constraint.

    Revision content adds a new contact person (pk=None) for a person who is
    already a live contact person (under a different pk), and at the same time
    reassigns that existing pk to a different person. Without renormalization
    of pk=None items, publishing INSERTs the new row before the existing row's
    person_id is rewritten, violating the unique constraint.
    """
    from wagtail.models import Revision

    from actions.models import ActionContactPerson
    from actions.tests.factories import ActionFactory
    from people.tests.factories import PersonFactory

    person_kept = PersonFactory.create()  # stays as moderator
    person_promoted = PersonFactory.create()  # currently moderator, becomes editor
    person_new = PersonFactory.create()  # new moderator replacing person_promoted

    action = ActionFactory.create(plan=plan)
    acp_kept = ActionContactPerson.objects.create(
        action=action,
        person=person_kept,
        role=ActionContactPerson.Role.MODERATOR,
        order=0,
    )
    acp_to_reassign = ActionContactPerson.objects.create(
        action=action,
        person=person_promoted,
        role=ActionContactPerson.Role.MODERATOR,
        order=1,
    )

    initial_revision = action.save_revision()
    revision_content = initial_revision.content.copy()
    if 'attributes' not in revision_content:
        revision_content['attributes'] = {}

    revision_content['contact_persons'] = [
        {
            'pk': None,
            'role': 'editor',
            'order': 0,
            'action': action.pk,
            'person': person_promoted.pk,
            'primary_contact': True,
        },
        {
            'pk': acp_kept.pk,
            'role': 'moderator',
            'order': 1,
            'action': action.pk,
            'person': person_kept.pk,
            'primary_contact': False,
        },
        {
            'pk': acp_to_reassign.pk,
            'role': 'moderator',
            'order': 2,
            'action': action.pk,
            'person': person_new.pk,
            'primary_contact': False,
        },
    ]

    revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    revision.content = revision_content
    revision.save()

    revision.publish()

    action.refresh_from_db()
    contacts_after = ActionContactPerson.objects.filter(action=action)
    assert contacts_after.count() == 3
    assert contacts_after.get(person=person_promoted).role == ActionContactPerson.Role.EDITOR
    assert contacts_after.get(person=person_kept).role == ActionContactPerson.Role.MODERATOR
    assert contacts_after.get(person=person_new).role == ActionContactPerson.Role.MODERATOR


def test_publish_with_duplicate_contact_person_in_revision_raises(plan):
    """
    Renormalization must not collapse duplicate (action, person) entries onto the same pk.

    If revision content contains two entries for the same person, the unique
    (action, person) constraint is already violated by the payload itself.
    Renormalization must not silently merge them onto one DB row (which would
    let one entry's role/order overwrite the other); the IntegrityError must
    surface so the caller can correct the data.
    """
    from django.db import IntegrityError
    from wagtail.models import Revision

    from actions.models import ActionContactPerson
    from actions.tests.factories import ActionFactory
    from people.tests.factories import PersonFactory

    person = PersonFactory.create()

    action = ActionFactory.create(plan=plan)
    existing = ActionContactPerson.objects.create(
        action=action,
        person=person,
        role=ActionContactPerson.Role.MODERATOR,
        order=0,
    )

    initial_revision = action.save_revision()
    revision_content = initial_revision.content.copy()
    if 'attributes' not in revision_content:
        revision_content['attributes'] = {}

    revision_content['contact_persons'] = [
        {
            'pk': existing.pk,
            'role': 'moderator',
            'order': 0,
            'action': action.pk,
            'person': person.pk,
            'primary_contact': False,
        },
        {
            'pk': None,
            'role': 'editor',
            'order': 1,
            'action': action.pk,
            'person': person.pk,
            'primary_contact': True,
        },
    ]

    revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    revision.content = revision_content
    revision.save()

    with pytest.raises(IntegrityError):
        revision.publish()


def test_publish_does_not_overwrite_order(plan):
    """
    Publishing a revision must not revert the action's order to the value stored in the revision.

    The order field is managed outside the revision workflow (e.g. via
    drag-and-drop reordering) and must be preserved.
    """
    from wagtail.models import Revision

    from actions.models import Action
    from actions.tests.factories import ActionFactory

    action = ActionFactory.create(plan=plan)
    action.order = 5
    action.save()

    # Create a revision that captures order=5.
    # save_revision() auto-publishes on non-workflow plans, which mutates
    # revision.content in-place (pops 'attributes' and 'order'), so we
    # need to reconstruct the content for our test revision.
    initial_revision = action.save_revision()
    revision_content = initial_revision.content.copy()
    revision_content.setdefault('attributes', {})
    revision_content['order'] = 5

    # Simulate an order change that happened after the revision was created
    Action.objects.filter(pk=action.pk).update(order=42)

    # Create a new revision from the old content and publish it
    new_revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    new_revision.content = revision_content
    new_revision.save()
    new_revision.publish()

    action.refresh_from_db()
    assert action.order == 42
