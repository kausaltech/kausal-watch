"""The reporting tab of the action edit view shows report snapshot values as text, never as markup."""

from __future__ import annotations

import re

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from actions.models import Action, AttributeType
from actions.tests.factories import AttributeRichTextFactory, AttributeTextFactory, AttributeTypeFactory
from admin_site.tests.factories import ClientPlanFactory
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

TEXT_PAYLOAD = '<img src=x onerror=alert(101)>'
# Draftail stores markup typed by the user as entities; `AttributeRichText.__str__` unescapes them again.
RICH_TEXT_PAYLOAD = '<p>&lt;img src=x onerror=alert(202)&gt;</p>'
RICH_TEXT_MARKUP = '<img src=x onerror=alert(202)>'


def _action_attribute_type(plan, format: AttributeType.AttributeFormat) -> AttributeType:
    return AttributeTypeFactory.create(
        scope=plan,
        object_content_type=ContentType.objects.get_for_model(Action),
        format=format,
    )


def _get_help_panels(
    client, plan, action, plan_admin_user, contact_person_user, text: str, rich_text: str
) -> tuple[str, list[str]]:
    """Return the whole edit page and the contents of the report's help panels on it."""
    text_type = _action_attribute_type(plan, AttributeType.AttributeFormat.TEXT)
    rich_text_type = _action_attribute_type(plan, AttributeType.AttributeFormat.RICH_TEXT)
    AttributeTextFactory.create(type=text_type, content_object=action, text=text)
    AttributeRichTextFactory.create(type=rich_text_type, content_object=action, text=rich_text)
    report_type = ReportTypeFactory.create(
        plan=plan,
        fields__0__attribute__attribute_type=text_type,
        fields__1__attribute__attribute_type=rich_text_type,
    )
    report = ReportFactory.create(type=report_type)
    report.fields = report_type.fields
    report.save()
    action.mark_as_complete_for_report(report, contact_person_user)

    ClientPlanFactory.create(plan=plan)
    client.force_login(plan_admin_user)
    response = client.get(reverse('wagtailsnippets_actions_action:edit', args=[action.pk]))
    assert response.status_code == 200
    content = response.content.decode()
    panel_re = rf'<legend class="w-sr-only">[^<]*\({re.escape(str(report))}\)</legend>\s*<div class="[^"]*">(.*?)</div>'
    panels = re.findall(panel_re, content, re.DOTALL)
    assert len(panels) == 2
    return content, panels


def test_snapshot_markup_is_escaped_in_help_panels(client, plan, action, plan_admin_user, action_contact_person_user):
    content, panels = _get_help_panels(
        client, plan, action, plan_admin_user, action_contact_person_user, TEXT_PAYLOAD, RICH_TEXT_PAYLOAD
    )

    assert TEXT_PAYLOAD not in content
    assert RICH_TEXT_MARKUP not in content
    assert panels == ['&lt;img src=x onerror=alert(101)&gt;', '&lt;img src=x onerror=alert(202)&gt;']


def test_harmless_snapshot_text_is_shown_escaped(client, plan, action, plan_admin_user, action_contact_person_user):
    _content, panels = _get_help_panels(
        client, plan, action, plan_admin_user, action_contact_person_user, 'Tom & Jerry', '<p>Rich &amp; famous</p>'
    )

    assert panels == ['Tom &amp; Jerry', 'Rich &amp; famous']
