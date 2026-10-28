"""The unit, quantity and indicator dimension admin views."""

from __future__ import annotations

import json
import re

from reversion.models import Version
from wagtail.models import ModelLogEntry

import pytest

from actions.tests.factories import PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from indicators.models import Dimension, PlanDimension, Quantity, Unit
from indicators.tests.factories import DimensionFactory, PlanDimensionFactory, QuantityFactory, UnitFactory

pytestmark = pytest.mark.django_db

UNITS_PATH = '/admin/indicators/unit/'
QUANTITIES_PATH = '/admin/indicators/quantity/'
DIMENSIONS_PATH = '/admin/indicators/dimension/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def own_dimension(plan_with_pages):
    return PlanDimensionFactory.create(plan=plan_with_pages, dimension__name='Own dimension').dimension


@pytest.fixture
def other_plan_dimension():
    return PlanDimensionFactory.create(plan=PlanFactory.create(), dimension__name='Other plan dimension').dimension


def _submenu_links(response_content: bytes, submenu_label: str) -> list[tuple[str, str]]:
    match = re.search(r'<script id="wagtail-sidebar-props" type="application/json">(.*?)</script>', response_content.decode())
    assert match is not None
    links: list[tuple[str, str]] = []

    def collect(node, inside: bool):
        if isinstance(node, dict):
            if node.get('_type') == 'wagtail.sidebar.SubMenuItem' and node['_args'][0]['label'] == submenu_label:
                inside = True
            if inside and node.get('_type') == 'wagtail.sidebar.LinkMenuItem':
                links.append((node['_args'][0]['label'], node['_args'][0]['url']))
            for value in node.values():
                collect(value, inside)
        elif isinstance(node, list):
            for value in node:
                collect(value, inside)

    collect(json.loads(match.group(1)), inside=False)
    return links


def _dimension_form_data(name: str) -> dict[str, str]:
    return {
        'name': name,
        'categories-TOTAL_FORMS': '0',
        'categories-INITIAL_FORMS': '0',
        'categories-MIN_NUM_FORMS': '0',
        'categories-MAX_NUM_FORMS': '1000',
    }


def test_indicator_menu_links_lookup_tables(admin_client):
    links = _submenu_links(admin_client.get('/admin/account/').content, 'Indicators')
    assert links == [
        ('Indicators', '/admin/indicators/indicator/'),
        ('Indicator dimensions', DIMENSIONS_PATH),
        ('Units', UNITS_PATH),
        ('Quantities', QUANTITIES_PATH),
    ]


def test_contact_person_has_no_lookup_table_access(client, action_contact_person_user, own_dimension):
    unit = UnitFactory.create()
    client.force_login(action_contact_person_user)
    for path in (UNITS_PATH, QUANTITIES_PATH, DIMENSIONS_PATH, f'{UNITS_PATH}edit/{unit.pk}/'):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response['Location'] == '/admin/', path


@pytest.mark.parametrize(('path', 'factory'), [(UNITS_PATH, UnitFactory), (QUANTITIES_PATH, QuantityFactory)])
def test_shared_lookup_table_listing_shows_all(admin_client, path, factory):
    instances = [factory.create(), factory.create()]
    response = admin_client.get(path)
    assert response.status_code == 200
    for instance in instances:
        assert f'{path}edit/{instance.pk}/' in response.content.decode()


def test_unit_listing_columns(admin_client):
    UnitFactory.create(name='kilogram', short_name='kg')
    content = admin_client.get(UNITS_PATH).content.decode()
    assert 'kilogram' in content
    assert '>kg<' in content


def test_quantity_listing_is_sorted_by_name(admin_client):
    QuantityFactory.create(name='Zinc')
    QuantityFactory.create(name='Argon')
    content = admin_client.get(QUANTITIES_PATH).content.decode()
    assert content.index('Argon') < content.index('Zinc')


def test_dimension_listing_shows_only_active_plan(admin_client, own_dimension, other_plan_dimension):
    response = admin_client.get(DIMENSIONS_PATH)
    assert response.status_code == 200
    content = response.content.decode()
    assert own_dimension.name in content
    assert other_plan_dimension.name not in content


@pytest.mark.parametrize('path', [UNITS_PATH, QUANTITIES_PATH, DIMENSIONS_PATH])
def test_listing_offers_no_bulk_delete(admin_client, own_dimension, path):
    UnitFactory.create()
    QuantityFactory.create()
    content = admin_client.get(path).content.decode()
    assert 'bulk-action' not in content


def test_bulk_delete_does_not_delete_dimension(admin_client, own_dimension):
    admin_client.post(f'/admin/bulk/indicators/dimension/delete/?id={own_dimension.pk}')
    assert Dimension.objects.filter(pk=own_dimension.pk).exists()


def test_creating_unit(admin_client):
    response = admin_client.get(UNITS_PATH)
    add_path = re.search(rf'href="({UNITS_PATH}(create|add)/)"', response.content.decode())
    assert add_path is not None

    response = admin_client.post(add_path.group(1), {'name': 'metre', 'short_name': 'm'})
    assert response.status_code == 302
    assert Unit.objects.filter(name='metre', short_name='m').exists()


def test_editing_unit_records_revision(admin_client, plan_admin_user):
    unit = UnitFactory.create(name='metre')
    response = admin_client.post(f'{UNITS_PATH}edit/{unit.pk}/', {'name': 'meter', 'short_name': 'm'})
    assert response.status_code == 302
    unit.refresh_from_db()
    assert unit.name == 'meter'
    version = Version.objects.get_for_object(unit).get()
    assert version.revision.user == plan_admin_user
    assert version.revision.get_comment() == "Unit 'meter' updated."


def test_editing_unit_writes_audit_log(admin_client, plan_admin_user):
    unit = UnitFactory.create(name='metre')
    admin_client.post(f'{UNITS_PATH}edit/{unit.pk}/', {'name': 'meter'})
    entry = ModelLogEntry.objects.get(object_id=str(unit.pk), action='wagtail.edit')
    assert entry.user == plan_admin_user


def test_editing_quantity_records_revision(admin_client, plan_admin_user):
    quantity = QuantityFactory.create(name='Mass')
    response = admin_client.post(f'{QUANTITIES_PATH}edit/{quantity.pk}/', {'name': 'Weight'})
    assert response.status_code == 302
    quantity.refresh_from_db()
    assert quantity.name == 'Weight'
    version = Version.objects.get_for_object(quantity).get()
    assert version.revision.user == plan_admin_user


def test_editing_quantity_saves_translation(admin_client):
    quantity = QuantityFactory.create(name='Mass')
    response = admin_client.post(f'{QUANTITIES_PATH}edit/{quantity.pk}/', {'name': 'Mass', 'name_fi': 'Massa'})
    assert response.status_code == 302
    quantity.refresh_from_db()
    assert quantity.name_fi == 'Massa'  # pyright: ignore[reportAttributeAccessIssue]


def test_editing_dimension_records_revision(admin_client, plan_admin_user, own_dimension):
    response = admin_client.post(f'{DIMENSIONS_PATH}edit/{own_dimension.pk}/', _dimension_form_data('Renamed'))
    assert response.status_code == 302
    own_dimension.refresh_from_db()
    assert own_dimension.name == 'Renamed'
    version = Version.objects.get_for_object(own_dimension).get()
    assert version.revision.user == plan_admin_user


def test_created_dimension_belongs_to_active_plan(admin_client, plan_with_pages):
    response = admin_client.get(DIMENSIONS_PATH)
    add_path = re.search(rf'href="({DIMENSIONS_PATH}(create|add)/)"', response.content.decode())
    assert add_path is not None

    data = _dimension_form_data('New dimension')
    data.update({
        'categories-TOTAL_FORMS': '1',
        'categories-0-name': 'First category',
        'categories-0-default_color': '#ff0000',
        'categories-0-ORDER': '1',
    })
    response = admin_client.post(add_path.group(1), data)
    assert response.status_code == 302
    dimension = Dimension.objects.get(name='New dimension')
    assert list(PlanDimension.objects.filter(dimension=dimension).values_list('plan', flat=True)) == [plan_with_pages.pk]
    assert [c.name for c in dimension.categories.all()] == ['First category']


def test_deleting_dimension(admin_client, own_dimension):
    response = admin_client.post(f'{DIMENSIONS_PATH}delete/{own_dimension.pk}/')
    assert response.status_code == 302
    assert not Dimension.objects.filter(pk=own_dimension.pk).exists()


def test_deleting_dimension_used_by_another_plan_is_refused(admin_client, own_dimension):
    PlanDimensionFactory.create(dimension=own_dimension, plan=PlanFactory.create())
    response = admin_client.post(f'{DIMENSIONS_PATH}delete/{own_dimension.pk}/', follow=True)
    assert Dimension.objects.filter(pk=own_dimension.pk).exists()
    assert response.redirect_chain[-1][0] == DIMENSIONS_PATH
    messages = [str(m) for m in response.context['messages']]
    assert f'Cannot delete dimension "{own_dimension.name}" at this time, please contact support.' in messages


def test_deleting_unit(admin_client):
    unit = UnitFactory.create()
    response = admin_client.post(f'{UNITS_PATH}delete/{unit.pk}/')
    assert response.status_code == 302
    assert not Unit.objects.filter(pk=unit.pk).exists()


def test_deleting_quantity(admin_client):
    quantity = QuantityFactory.create()
    response = admin_client.post(f'{QUANTITIES_PATH}delete/{quantity.pk}/')
    assert response.status_code == 302
    assert not Quantity.objects.filter(pk=quantity.pk).exists()


def test_dimension_without_plan_is_not_listed(admin_client):
    dimension = DimensionFactory.create(name='Planless dimension')
    assert dimension.name not in admin_client.get(DIMENSIONS_PATH).content.decode()
