from __future__ import annotations

from django.urls import reverse
from reversion.models import Version

import pytest

from admin_site.tests.factories import ClientPlanFactory

pytestmark = pytest.mark.django_db


def test_snippet_edit_creates_one_reversion_version(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    content = plan_with_pages.general_content
    edit_url = reverse('wagtailsnippets_content_sitegeneralcontent:edit', args=(content.pk,))
    form = client.get(edit_url).context['form']
    data = {name: value for name in form.fields if (value := form[name].value()) not in (None, False)}
    data['site_title'] = 'Edited title'

    response = client.post(edit_url, data)

    assert response.status_code == 302
    assert Version.objects.get_for_object(content).count() == 1
