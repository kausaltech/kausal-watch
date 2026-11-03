"""The common indicator admin views."""

from __future__ import annotations

import html
import re

import pytest

from actions.tests.factories import PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data, submenu_links
from indicators.models import CommonIndicator
from indicators.tests.factories import (
    CommonIndicatorFactory,
    DimensionFactory,
    IndicatorFactory,
    QuantityFactory,
    UnitFactory,
)

pytestmark = pytest.mark.django_db

COMMON_INDICATORS_PATH = '/admin/indicators/commonindicator/'


@pytest.fixture
def superuser_client(client, plan_with_pages, superuser):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(superuser)
    return client


def _add_path(response_content: bytes) -> str:
    match = re.search(rf'href="({COMMON_INDICATORS_PATH}(?:create|add)/[^"]*)"', response_content.decode())
    assert match is not None
    return html.unescape(match.group(1))


def test_indicator_menu_links_common_indicators_for_superusers(superuser_client):
    links = submenu_links(superuser_client.get('/admin/account/').content, 'Indicators')
    assert links[:2] == [
        ('Indicators', '/admin/indicators/indicator/'),
        ('Common indicators', COMMON_INDICATORS_PATH),
    ]


def test_plan_admin_has_no_access(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    common_indicator = CommonIndicatorFactory.create()
    client.force_login(plan_admin_user)
    links = submenu_links(client.get('/admin/account/').content, 'Indicators')
    assert not any(label == 'Common indicators' for label, _url in links)
    for path in (COMMON_INDICATORS_PATH, f'{COMMON_INDICATORS_PATH}edit/{common_indicator.pk}/'):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response['Location'] == '/admin/', path


def test_listing_shows_all_common_indicators(superuser_client):
    own = CommonIndicatorFactory.create(name='Emissions', unit__short_name='kt', quantity__name='Mass')
    other = CommonIndicatorFactory.create(name='Energy')
    PlanFactory.create().common_indicators.add(other)
    content = superuser_client.get(COMMON_INDICATORS_PATH).content.decode()
    assert f'{COMMON_INDICATORS_PATH}edit/{own.pk}/' in content
    assert f'{COMMON_INDICATORS_PATH}edit/{other.pk}/' in content
    assert re.search(r'>\s*kt\s*<', content)
    assert 'Mass' in content


def test_listing_unit_falls_back_to_name(superuser_client):
    CommonIndicatorFactory.create(unit__name='tonne', unit__short_name='')
    assert re.search(r'>\s*tonne\s*<', superuser_client.get(COMMON_INDICATORS_PATH).content.decode())


def test_listing_can_be_searched_by_name(superuser_client):
    match = CommonIndicatorFactory.create(name='Emissions')
    other = CommonIndicatorFactory.create(name='Energy')
    content = superuser_client.get(f'{COMMON_INDICATORS_PATH}?q=Emiss').content.decode()
    assert f'{COMMON_INDICATORS_PATH}edit/{match.pk}/' in content
    assert f'{COMMON_INDICATORS_PATH}edit/{other.pk}/' not in content


def test_creating_common_indicator(superuser_client):
    add_path = _add_path(superuser_client.get(COMMON_INDICATORS_PATH).content)
    form = superuser_client.get(add_path).context['form']
    assert {'identifier', 'name', 'quantity', 'unit', 'description'} <= set(form.fields)
    assert 'dimensions' in form.formsets
    dimension = DimensionFactory.create()
    data = post_data(form)
    data.update({
        'identifier': 'emissions',
        'name': 'Emissions',
        'quantity': QuantityFactory.create().pk,
        'unit': UnitFactory.create().pk,
        'dimensions-TOTAL_FORMS': '1',
        'dimensions-0-dimension': dimension.pk,
        'dimensions-0-ORDER': '1',
    })
    response = superuser_client.post(add_path, data)
    assert response.status_code == 302
    assert response['Location'] == COMMON_INDICATORS_PATH
    common_indicator = CommonIndicator.objects.get(identifier='emissions')
    assert list(common_indicator.dimensions.values_list('dimension', flat=True)) == [dimension.pk]


def test_common_indicator_without_indicators_can_change_quantity_unit_and_dimensions(superuser_client):
    common_indicator = CommonIndicatorFactory.create()
    form = superuser_client.get(f'{COMMON_INDICATORS_PATH}edit/{common_indicator.pk}/').context['form']
    assert {'quantity', 'unit'} <= set(form.fields)
    assert 'dimensions' in form.formsets


def test_common_indicator_with_indicators_cannot_change_quantity_unit_and_dimensions(superuser_client):
    common_indicator = CommonIndicatorFactory.create()
    IndicatorFactory.create(common=common_indicator, quantity=common_indicator.quantity, unit=common_indicator.unit)
    response = superuser_client.get(f'{COMMON_INDICATORS_PATH}edit/{common_indicator.pk}/')
    form = response.context['form']
    assert 'quantity' not in form.fields
    assert 'unit' not in form.fields
    assert 'dimensions' not in form.formsets
    assert 'This common indicator has indicators linked to it' in response.content.decode()


def test_editing_common_indicator_saves_and_redirects(superuser_client):
    common_indicator = CommonIndicatorFactory.create()
    path = f'{COMMON_INDICATORS_PATH}edit/{common_indicator.pk}/'
    data = post_data(superuser_client.get(path).context['form'])
    data['name'] = 'Renamed'
    del data['description']  # Draftail expects its JSON format, not the stored HTML
    response = superuser_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == COMMON_INDICATORS_PATH
    common_indicator.refresh_from_db()
    assert common_indicator.name == 'Renamed'


def test_deleting_common_indicator(superuser_client):
    common_indicator = CommonIndicatorFactory.create()
    response = superuser_client.post(f'{COMMON_INDICATORS_PATH}delete/{common_indicator.pk}/')
    assert response.status_code == 302
    assert response['Location'] == COMMON_INDICATORS_PATH
    assert not CommonIndicator.objects.filter(pk=common_indicator.pk).exists()
