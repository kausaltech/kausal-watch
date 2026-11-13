"""The indicator admin views."""

from __future__ import annotations

import html
import re

from wagtail.admin.rich_text import DraftailRichTextArea

import pytest

from actions.tests.factories import CategoryFactory, CategoryTypeFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data, submenu_links
from indicators.models import Indicator, IndicatorLevel
from indicators.tests.factories import (
    IndicatorContactFactory,
    IndicatorDimensionFactory,
    IndicatorFactory,
    IndicatorLevelFactory,
    IndicatorValueFactory,
    QuantityFactory,
    UnitFactory,
)
from orgs.tests.factories import OrganizationFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

INDICATORS_PATH = '/admin/indicators/indicator/'


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


def _indicator(plan, **kwargs) -> Indicator:
    kwargs.setdefault('organization', plan.organization)
    return IndicatorFactory.create(plans=[plan], common=None, **kwargs)


def _edit_path(indicator: Indicator) -> str:
    return f'{INDICATORS_PATH}edit/{indicator.pk}/'


def _add_path(response_content: bytes) -> str | None:
    match = re.search(rf'href="({INDICATORS_PATH}(?:create|add)/[^"]*)"', response_content.decode())
    return html.unescape(match.group(1)) if match else None


@pytest.fixture
def indicator_contact_client(client, plan_with_pages):
    ClientPlanFactory.create(plan=plan_with_pages)
    contact = IndicatorContactFactory.create(indicator=_indicator(plan_with_pages, name='Own indicator'))
    assert contact.person.user is not None
    client.force_login(contact.person.user)
    client.indicator = contact.indicator
    return client


def test_indicator_menu_links_indicators(admin_client):
    links = submenu_links(admin_client.get('/admin/account/').content, 'Indicators')
    assert links[0] == ('Indicators', INDICATORS_PATH)


def test_listing_shows_active_plan_indicators(admin_client, plan_with_pages):
    own = _indicator(plan_with_pages)
    other_plan = _indicator(PlanFactory.create())
    content = admin_client.get(INDICATORS_PATH).content.decode()
    assert _edit_path(own) in content
    assert _edit_path(other_plan) not in content


def test_listing_filter_shows_indicators_not_in_active_plan(admin_client, plan_with_pages):
    own = _indicator(plan_with_pages)
    unconnected = IndicatorFactory.create(organization=plan_with_pages.organization, common=None)
    default = admin_client.get(INDICATORS_PATH).content.decode()
    assert _edit_path(unconnected) not in default
    not_in_plan = admin_client.get(f'{INDICATORS_PATH}?disconnected=2').content.decode()
    assert _edit_path(unconnected) in not_in_plan
    assert _edit_path(own) not in not_in_plan
    everything = admin_client.get(f'{INDICATORS_PATH}?disconnected=1').content.decode()
    assert _edit_path(unconnected) in everything
    assert _edit_path(own) in everything


def test_listing_columns(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages, name='Emissions', unit=UnitFactory.create(short_name='kt'), quantity__name='Mass')
    IndicatorValueFactory.create(indicator=indicator)
    content = admin_client.get(INDICATORS_PATH).content.decode()
    assert 'Emissions' in content
    assert plan_with_pages.organization.name in content
    assert re.search(r'>\s*kt\s*<', content)
    assert 'Mass' in content


def test_listing_can_be_searched_by_name(admin_client, plan_with_pages):
    match = _indicator(plan_with_pages, name='Emissions')
    other = _indicator(plan_with_pages, name='Energy')
    content = admin_client.get(f'{INDICATORS_PATH}?q=Emiss').content.decode()
    assert _edit_path(match) in content
    assert _edit_path(other) not in content


def test_plan_admin_has_no_organization_filter(admin_client, plan_with_pages):
    _indicator(plan_with_pages)
    assert 'organization=' not in admin_client.get(INDICATORS_PATH).content.decode()


def test_superuser_can_filter_by_organization(superuser_client, plan_with_pages):
    own = _indicator(plan_with_pages)
    other_org = OrganizationFactory.create()
    plan_with_pages.related_organizations.add(other_org)
    other = _indicator(plan_with_pages, organization=other_org)
    content = superuser_client.get(f'{INDICATORS_PATH}?organization={other_org.pk}').content.decode()
    assert _edit_path(other) in content
    assert _edit_path(own) not in content


def test_action_contact_person_sees_listing_but_cannot_edit(client, plan_with_pages, action_contact_person_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    indicator = _indicator(plan_with_pages)
    client.force_login(action_contact_person_user)
    response = client.get(INDICATORS_PATH)
    assert response.status_code == 200
    content = response.content.decode()
    assert indicator.name in content
    assert _edit_path(indicator) not in content
    assert _add_path(response.content) is None
    response = client.get(_edit_path(indicator))
    assert response.status_code == 302
    assert response['Location'] == '/admin/'


def test_indicator_contact_person_edits_own_indicator_only(indicator_contact_client, plan_with_pages):
    own = indicator_contact_client.indicator
    other = _indicator(plan_with_pages)
    response = indicator_contact_client.get(INDICATORS_PATH)
    content = response.content.decode()
    assert _edit_path(own) in content
    assert _edit_path(other) not in content
    assert _add_path(response.content) is None
    assert indicator_contact_client.get(_edit_path(own)).status_code == 200
    assert indicator_contact_client.get(_edit_path(other)).status_code == 302


def _post_data(form) -> dict:
    data = post_data(form)
    # Draftail expects its JSON format, not the stored HTML
    for name, field in form.fields.items():
        if isinstance(field.widget, DraftailRichTextArea):
            data.pop(name, None)
    return data


def _creation_data(client, plan) -> tuple[str, dict]:
    add_path = _add_path(client.get(INDICATORS_PATH).content)
    assert add_path is not None
    data = _post_data(client.get(add_path).context['form'])
    data.update({
        'name': 'Emissions',
        'time_resolution': 'year',
        'level': 'tactical',
        'quantity': QuantityFactory.create().pk,
        'unit': UnitFactory.create().pk,
        'organization': plan.organization.pk,
    })
    return add_path, data


def test_creating_indicator_connects_it_to_the_active_plan(admin_client, plan_with_pages):
    add_path, data = _creation_data(admin_client, plan_with_pages)
    response = admin_client.post(add_path, data)
    assert response.status_code == 302
    assert response['Location'] == INDICATORS_PATH
    indicator = Indicator.objects.get(name='Emissions')
    assert IndicatorLevel.objects.get(indicator=indicator).plan == plan_with_pages
    assert IndicatorLevel.objects.get(indicator=indicator).level == 'tactical'


def test_creating_indicator_leads_to_change_history_message(admin_client, plan_with_pages):
    plan_with_pages.features.enable_change_log = True
    plan_with_pages.features.save()
    add_path, data = _creation_data(admin_client, plan_with_pages)
    response = admin_client.post(add_path, data)
    indicator = Indicator.objects.get(name='Emissions')
    assert response['Location'] == f'/admin/snippets/actions/indicatorchangelogmessage/add/?indicator={indicator.pk}'


def test_edit_form_tabs(admin_client, plan_with_pages):
    plan_with_pages.other_languages = ['fi']
    plan_with_pages.save()
    form = admin_client.get(_edit_path(_indicator(plan_with_pages))).context['form']
    assert {'name', 'level', 'quantity', 'unit', 'visibility', 'internal_notes', 'common', 'name_fi'} <= set(form.fields)
    assert {'dimensions', 'contact_persons', 'related_actions', 'related_effects', 'related_causes'} <= set(form.formsets)


def test_edit_form_of_common_indicator_instance(admin_client, plan_with_pages):
    indicator = IndicatorFactory.create(plans=[plan_with_pages], organization=plan_with_pages.organization)
    response = admin_client.get(_edit_path(indicator))
    form = response.context['form']
    assert 'quantity' not in form.fields
    assert 'unit' not in form.fields
    assert 'dimensions' not in form.formsets
    assert 'This indicator is linked to a common indicator' in response.content.decode()


def test_edit_form_of_indicator_contact_person(indicator_contact_client):
    form = indicator_contact_client.get(_edit_path(indicator_contact_client.indicator)).context['form']
    assert 'visibility' not in form.fields
    assert 'dimensions' not in form.formsets
    assert 'name' in form.fields


def test_edit_form_warns_that_changing_dimensions_deletes_values(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    content = admin_client.get(_edit_path(indicator)).content.decode()
    assert 'If you change the dimensions of this indicator' not in content
    assert 'reference_value' in admin_client.get(_edit_path(indicator)).context['form'].fields
    IndicatorValueFactory.create(indicator=indicator)
    assert 'If you change the dimensions of this indicator' in admin_client.get(_edit_path(indicator)).content.decode()


def test_edit_form_offers_reference_value_only_without_dimensions(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    IndicatorDimensionFactory.create(indicator=indicator)
    assert 'reference_value' not in admin_client.get(_edit_path(indicator)).context['form'].fields


def test_edit_form_offers_paths_node_only_with_paths_instance(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    plan_with_pages.kausal_paths_instance_uuid = ''
    plan_with_pages.save()
    assert 'kausal_paths_node_uuid' not in admin_client.get(_edit_path(indicator)).context['form'].fields
    plan_with_pages.kausal_paths_instance_uuid = 'instance'
    plan_with_pages.save()
    assert 'kausal_paths_node_uuid' in admin_client.get(_edit_path(indicator)).context['form'].fields


def test_editing_saves_categories(admin_client, plan_with_pages):
    category_type = CategoryTypeFactory.create(plan=plan_with_pages, usable_for_indicators=True, editable_for_indicators=True)
    category = CategoryFactory.create(type=category_type)
    indicator = _indicator(plan_with_pages)
    path = _edit_path(indicator)
    field_name = f'categories_{category_type.identifier}'
    data = _post_data(admin_client.get(path).context['form'])
    data[field_name] = [category.pk]
    assert admin_client.post(path, data).status_code == 302
    assert list(indicator.categories.all()) == [category]


def test_editing_saves_and_redirects(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    path = _edit_path(indicator)
    data = _post_data(admin_client.get(path).context['form'])
    data['name'] = 'Renamed'
    data['level'] = 'operational'
    response = admin_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == INDICATORS_PATH
    indicator.refresh_from_db()
    assert indicator.name == 'Renamed'
    assert IndicatorLevel.objects.get(indicator=indicator, plan=plan_with_pages).level == 'operational'


def test_editing_without_level_removes_indicator_from_plan(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    path = _edit_path(indicator)
    data = _post_data(admin_client.get(path).context['form'])
    data['level'] = ''
    assert admin_client.post(path, data).status_code == 302
    assert not IndicatorLevel.objects.filter(indicator=indicator, plan=plan_with_pages).exists()


def test_editing_leads_to_change_history_message(admin_client, plan_with_pages):
    plan_with_pages.features.enable_change_log = True
    plan_with_pages.features.save()
    indicator = _indicator(plan_with_pages)
    path = _edit_path(indicator)
    response = admin_client.post(path, _post_data(admin_client.get(path).context['form']))
    assert response['Location'] == f'/admin/snippets/actions/indicatorchangelogmessage/add/?indicator={indicator.pk}'


def test_editing_after_switching_plans_saves_for_the_original_plan(client, plan_with_pages):
    other_plan = PlanFactory.create()
    for plan in (plan_with_pages, other_plan):
        ClientPlanFactory.create(plan=plan)
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan_with_pages, other_plan])
    user.selected_admin_plan = plan_with_pages
    user.save()
    client.force_login(user)
    indicator = _indicator(plan_with_pages)
    IndicatorLevelFactory.create(indicator=indicator, plan=other_plan, level='strategic')
    path = _edit_path(indicator)
    data = _post_data(client.get(path).context['form'])
    data['level'] = 'operational'
    user.selected_admin_plan = other_plan
    user.save()
    response = client.post(path, data, follow=True)
    assert any('you have switched to a different plan' in str(m) for m in response.context['messages'])
    assert IndicatorLevel.objects.get(indicator=indicator, plan=plan_with_pages).level == 'operational'
    assert IndicatorLevel.objects.get(indicator=indicator, plan=other_plan).level == 'strategic'


def test_deleting_indicator(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    response = admin_client.post(f'{INDICATORS_PATH}delete/{indicator.pk}/')
    assert response.status_code == 302
    assert response['Location'] == INDICATORS_PATH
    assert not Indicator.objects.filter(pk=indicator.pk).exists()


def test_indicator_of_another_plan_too_is_not_deleted(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    indicator.plans.add(PlanFactory.create())
    admin_client.post(f'{INDICATORS_PATH}delete/{indicator.pk}/')
    assert Indicator.objects.filter(pk=indicator.pk).exists()


def test_indicator_contact_person_cannot_delete(indicator_contact_client):
    indicator = indicator_contact_client.indicator
    indicator_contact_client.post(f'{INDICATORS_PATH}delete/{indicator.pk}/')
    assert Indicator.objects.filter(pk=indicator.pk).exists()


def test_editing_indicator_of_another_own_plan_offers_a_plan_switch(client, plan_with_pages):
    other_plan = PlanFactory.create()
    for plan in (plan_with_pages, other_plan):
        ClientPlanFactory.create(plan=plan)
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan_with_pages, other_plan])
    user.selected_admin_plan = plan_with_pages
    user.save()
    client.force_login(user)
    indicator = _indicator(other_plan)
    response = client.get(_edit_path(indicator))
    assert response.status_code == 302
    assert response['Location'].startswith(f'/admin/change-admin-plan/{other_plan.pk}/')


def test_indicator_contact_person_cannot_create(indicator_contact_client):
    response = indicator_contact_client.get(f'{INDICATORS_PATH}add/')
    assert response.status_code == 302
    assert response['Location'] == '/admin/'


def test_adding_a_factor_returns_to_the_factors_panel(admin_client, plan_with_pages):
    plan_with_pages.features.enable_indicator_factors = True
    plan_with_pages.features.save()
    indicator = _indicator(plan_with_pages)
    path = _edit_path(indicator)
    data = _post_data(admin_client.get(path).context['form'])
    data.update({
        '_active_tab': '#tab-relationships',
        'metrics-TOTAL_FORMS': '1',
        'metrics-0-label': 'Emission factor',
        'metrics-0-unit': 't',
        'metrics-0-result_label': 'Emissions',
    })
    response = admin_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == f'{path}#panel-child-relationships-factors-section'
    indicator.refresh_from_db()
    assert indicator.dataset_schema is not None
    assert list(indicator.dataset_schema.metrics.values_list('label', flat=True)) == ['Emission factor', 'Emissions']


def test_listing_links_to_the_live_indicator(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    view_url = indicator.get_view_url(plan=plan_with_pages)
    assert view_url
    content = html.unescape(admin_client.get(INDICATORS_PATH).content.decode())
    assert f'href="{view_url}"' in content
    assert 'View live' in content


def test_bulk_delete_is_not_available(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    admin_client.post(f'/admin/bulk/indicators/indicator/delete/?id={indicator.pk}')
    assert Indicator.objects.filter(pk=indicator.pk).exists()


def test_listing_menu_labels_editing_the_indicator_apart_from_its_data(admin_client, plan_with_pages):
    _indicator(plan_with_pages)
    assert 'Edit properties' in admin_client.get(INDICATORS_PATH).content.decode()


def test_history_of_own_plan_indicator(admin_client, plan_with_pages):
    indicator = _indicator(plan_with_pages)
    assert admin_client.get(f'{INDICATORS_PATH}history/{indicator.pk}/').status_code == 200


def test_history_of_other_plan_indicator_is_refused(admin_client):
    other_plan = PlanFactory.create()
    indicator = _indicator(other_plan)
    assert admin_client.get(f'{INDICATORS_PATH}history/{indicator.pk}/').status_code == 302


class TestDeletingIndicatorShownOnPages:
    """Deleting an indicator must not leave content blocks pointing at a missing indicator."""

    @staticmethod
    def _delete_path(indicator: Indicator) -> str:
        return f'{INDICATORS_PATH}delete/{indicator.pk}/'

    @staticmethod
    def _group_block(indicator: Indicator) -> tuple[str, dict[str, object]]:
        return ('indicator_group', {'title': '', 'indicators': [{'indicator': indicator, 'style': 'graph'}]})

    def test_indicator_in_published_block_cannot_be_deleted(self, admin_client, plan_with_pages):
        from actions.perms import sync_plan_admin_group_permissions

        # Give the plan admins the page permissions that the site, created after the plan, lacks so far
        sync_plan_admin_group_permissions(plan_with_pages)
        indicator = _indicator(plan_with_pages)
        page = plan_with_pages.root_page.specific
        page.body = [self._group_block(indicator)]
        page.save()

        response = admin_client.get(self._delete_path(indicator))
        assert response.status_code == 200
        assert response.context['indicator_usage'].pages == [page]
        assert f'/pages/{page.pk}/edit/'.encode() in response.content
        assert b'Yes, delete' not in response.content

        response = admin_client.post(self._delete_path(indicator))
        assert response.status_code == 200
        assert Indicator.objects.filter(pk=indicator.pk).exists()

    def test_indicator_only_in_draft_cannot_be_deleted(self, admin_client, plan_with_pages):
        indicator = _indicator(plan_with_pages)
        page = plan_with_pages.root_page.specific
        page.body = [self._group_block(indicator)]
        page.save_revision()

        usage = admin_client.get(self._delete_path(indicator)).context['indicator_usage']
        assert usage.pages == []
        assert [p.pk for p in usage.draft_pages] == [page.pk]

        admin_client.post(self._delete_path(indicator))
        assert Indicator.objects.filter(pk=indicator.pk).exists()

    def test_indicator_nested_in_dashboard_row_cannot_be_deleted(self, admin_client, plan_with_pages):
        indicator = _indicator(plan_with_pages)
        page = plan_with_pages.root_page.specific
        page.body = [('dashboard_row', [('indicator_summary', {'indicator': indicator})])]
        page.save()

        admin_client.post(self._delete_path(indicator))
        assert Indicator.objects.filter(pk=indicator.pk).exists()

    def test_indicator_shown_on_page_of_plan_it_left_cannot_be_deleted(self, admin_client, plan_with_pages):
        from actions.tests.factories import PlanFactory

        indicator = _indicator(plan_with_pages)
        other_plan = PlanFactory.create()
        other_plan.create_default_site()
        page = other_plan.root_page.specific
        page.body = [self._group_block(indicator)]
        page.save()

        response = admin_client.get(self._delete_path(indicator))
        assert response.context['indicator_usage'].pages == [page]
        # The page belongs to a plan the user can't administer, so it is not revealed
        assert response.context['using_pages'][0]['can_edit'] is False
        assert page.title.encode() not in response.content
        assert f'/pages/{page.pk}/edit/'.encode() not in response.content
        assert b'have access to' in response.content

    def test_indicator_only_in_draft_of_plan_it_left_cannot_be_deleted(self, admin_client, plan_with_pages):
        from actions.tests.factories import PlanFactory

        indicator = _indicator(plan_with_pages)
        other_plan = PlanFactory.create()
        other_plan.create_default_site()
        page = other_plan.root_page.specific
        page.body = [self._group_block(indicator)]
        page.save_revision()

        usage = admin_client.get(self._delete_path(indicator)).context['indicator_usage']
        assert [p.pk for p in usage.draft_pages] == [page.pk]

    def test_block_with_other_indicator_does_not_block_deletion(self, admin_client, plan_with_pages):
        indicator = _indicator(plan_with_pages)
        page = plan_with_pages.root_page.specific
        page.body = [self._group_block(_indicator(plan_with_pages))]
        page.save()

        response = admin_client.post(self._delete_path(indicator))
        assert response.status_code == 302
        assert not Indicator.objects.filter(pk=indicator.pk).exists()

    def test_rich_text_link_does_not_block_deletion(self, admin_client, plan_with_pages):
        from wagtail.rich_text import RichText

        indicator = _indicator(plan_with_pages)
        page = plan_with_pages.root_page.specific
        link = f'<p><a linktype="indicator" id="{indicator.pk}" uuid="{indicator.uuid}">link</a></p>'
        page.body = [('text', RichText(link))]
        page.save()

        response = admin_client.post(self._delete_path(indicator))
        assert response.status_code == 302
        assert not Indicator.objects.filter(pk=indicator.pk).exists()
