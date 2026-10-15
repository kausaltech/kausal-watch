from __future__ import annotations

import typing

from django.urls import reverse

import pytest

from admin_site.tests.factories import ClientPlanFactory
from indicators.tests.factories import QuantityFactory, UnitFactory
from indicators.wagtail_admin import QuantityAdmin, UnitAdmin

if typing.TYPE_CHECKING:
    from django.test import Client

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(('admin_class', 'factory'), [(UnitAdmin, UnitFactory), (QuantityAdmin, QuantityFactory)])
def test_untranslated_fields_tab_names_default_language(
    client: Client,
    plan: Plan,
    plan_admin_user: User,
    admin_class: type[UnitAdmin | QuantityAdmin],
    factory: type[UnitFactory | QuantityFactory],
):
    # Units and quantities are shared between plans, so their untranslated fields are always in English, not in the
    # primary language of the active plan. There is no separate English tab, so the tab holding these fields must say so.
    ClientPlanFactory.create(plan=plan)
    instance = factory.create()
    client.force_login(plan_admin_user)
    edit_url = reverse(admin_class().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': instance.pk})
    response = client.get(edit_url)
    assert response.status_code == 200
    headings = [str(tab.heading) for tab in response.context['edit_handler'].children]
    assert headings[0] == 'General (English (United States))'
    assert 'English (United States)' not in headings
