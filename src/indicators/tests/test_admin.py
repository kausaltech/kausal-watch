from __future__ import annotations

import typing

from django.urls import reverse
from wagtail.admin.rich_text import DraftailRichTextArea

import pytest

from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data
from indicators.tests.factories import (
    DimensionFactory,
    IndicatorDimensionFactory,
    IndicatorFactory,
    IndicatorLevelFactory,
    QuantityFactory,
    UnitFactory,
)

if typing.TYPE_CHECKING:
    from django.test import Client

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ('url_name', 'factory'),
    [('wagtailsnippets_indicators_unit:edit', UnitFactory), ('wagtailsnippets_indicators_quantity:edit', QuantityFactory)],
)
def test_untranslated_fields_tab_names_default_language(
    client: Client,
    plan: Plan,
    plan_admin_user: User,
    url_name: str,
    factory: type[UnitFactory | QuantityFactory],
):
    # Units and quantities are shared between plans, so their untranslated fields are always in English, not in the
    # primary language of the active plan. There is no separate English tab, so the tab holding these fields must say so.
    ClientPlanFactory.create(plan=plan)
    instance = factory.create()
    client.force_login(plan_admin_user)
    edit_url = reverse(url_name, args=(instance.pk,))
    response = client.get(edit_url)
    assert response.status_code == 200
    headings = [str(tab.heading) for tab in response.context['panel'].children]
    assert headings[0] == 'General (English (United States))'
    assert 'English (United States)' not in headings


def test_grouping_dimension_removed_from_dimensions_in_same_save_is_rejected(
    client: Client,
    plan: Plan,
    plan_admin_user: User,
):
    # Picking a grouping dimension while removing it from the dimensions must give a form error, not a server error.
    ClientPlanFactory.create(plan=plan)
    indicator = IndicatorFactory.create(organization=plan.organization, common=None)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    removed = DimensionFactory.create()
    kept = DimensionFactory.create()
    IndicatorDimensionFactory.create(indicator=indicator, dimension=removed, order=0)
    IndicatorDimensionFactory.create(indicator=indicator, dimension=kept, order=1)
    client.force_login(plan_admin_user)
    edit_url = f'/admin/indicators/indicator/edit/{indicator.pk}/'
    form = client.get(edit_url).context['form']
    data = post_data(form)
    # post_data() gives rich text as HTML, but Draftail posts its own JSON; leave those fields out.
    for name, field in form.fields.items():
        if isinstance(field.widget, DraftailRichTextArea):
            data.pop(name, None)
    data['grouping_dimension'] = removed.pk
    removed_form = next(f for f in form.formsets['dimensions'].forms if f.instance.dimension_id == removed.pk)
    data[f'{removed_form.prefix}-DELETE'] = 'on'

    response = client.post(edit_url, data)

    assert response.status_code == 200
    assert 'grouping_dimension' in response.context['form'].errors
    indicator.refresh_from_db()
    assert indicator.grouping_dimension is None
    assert set(indicator.dimensions.values_list('dimension', flat=True)) == {removed.pk, kept.pk}
