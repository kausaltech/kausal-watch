from __future__ import annotations

import re

from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from wagtail.admin.panels import FieldPanel, ObjectList
from wagtail.admin.widgets import AdminAutoHeightTextInput

import pytest

from actions.models import ActionStatus, Plan
from actions.tests.factories import ActionStatusFactory, PlanFactory
from actions.wagtail_admin import PlanViewSet
from admin_site.tests.factories import ClientPlanFactory
from admin_site.wagtail import TranslationsPanel, insert_model_translation_panels

pytestmark = pytest.mark.django_db


def _bound_translations_panel(rf, instance: ActionStatus, data: dict[str, str] | None = None):
    edit_handler = ObjectList([
        FieldPanel('name'),
        TranslationsPanel([FieldPanel('name_fi', heading='Finnish')]),
    ]).bind_to_model(ActionStatus)
    form_class = edit_handler.get_form_class()
    form = form_class(instance=instance, data=data) if data is not None else form_class(instance=instance)
    if data is not None:
        form.is_valid()
    request = rf.get('/')
    request.user = AnonymousUser()
    bound = edit_handler.get_bound_panel(instance=instance, request=request, form=form)
    # `children` comes from PanelGroup.BoundPanel at runtime; the Wagtail stubs leave it off ObjectList.BoundPanel
    children = bound.children  # type: ignore[attr-defined]
    return next(child for child in children if isinstance(child, TranslationsPanel.BoundPanel))


class TestInsertModelTranslationPanels:
    def test_translations_follow_their_field_in_one_section(self, rf):
        plan = PlanFactory.create(other_languages=['fi', 'sv'])
        request = rf.get('/')

        panels = insert_model_translation_panels(ActionStatus, [FieldPanel('identifier'), FieldPanel('name')], request, plan)

        assert [type(p).__name__ for p in panels] == ['FieldPanel', 'FieldPanel', 'TranslationsPanel']
        section = panels[2]
        assert isinstance(section, TranslationsPanel)
        assert [child.field_name for child in section.children] == ['name_fi', 'name_sv']  # type: ignore[attr-defined]
        # Only the language is visible; the field name is there for screen readers
        assert [str(child.heading) for child in section.children] == [
            '<span class="w-sr-only">Name: </span>Finnish',
            '<span class="w-sr-only">Name: </span>Swedish',
        ]

    def test_translations_use_the_widget_of_their_field(self, rf):
        # Long texts get Wagtail's auto-height textarea; their translations must too, not a 10-row textarea.
        plan = PlanFactory.create(other_languages=['fi'])

        panels = insert_model_translation_panels(
            Plan, [FieldPanel('pledge_account_description'), FieldPanel('pledge_account_title')], rf.get('/'), plan
        )

        description_fi, title_fi = (panel.children[0] for panel in panels if isinstance(panel, TranslationsPanel))
        assert description_fi.widget is AdminAutoHeightTextInput  # type: ignore[attr-defined]
        assert title_fi.widget is None  # type: ignore[attr-defined]

    def test_hidden_label_uses_the_panel_heading_when_it_has_one(self, rf):
        plan = PlanFactory.create(other_languages=['fi'])

        panels = insert_model_translation_panels(ActionStatus, [FieldPanel('name', heading='Status')], rf.get('/'), plan)

        section = panels[1]
        assert isinstance(section, TranslationsPanel)
        assert str(section.children[0].heading) == '<span class="w-sr-only">Status: </span>Finnish'

    def test_no_section_without_other_languages(self, rf):
        plan = PlanFactory.create(other_languages=[])

        panels = insert_model_translation_panels(ActionStatus, [FieldPanel('name')], rf.get('/'), plan)

        assert [type(p).__name__ for p in panels] == ['FieldPanel']


class TestTranslationsPanelOpenState:
    def test_open_when_a_translation_is_empty(self, rf):
        status = ActionStatusFactory.create(name='In progress')

        assert _bound_translations_panel(rf, status).is_open is True

    def test_folded_when_every_translation_is_filled(self, rf):
        status = ActionStatusFactory.create(name='In progress')
        status.name_fi = 'Käynnissä'  # type: ignore[attr-defined]
        status.save()

        assert _bound_translations_panel(rf, status).is_open is False

    def test_open_when_a_translation_has_an_error(self, rf):
        status = ActionStatusFactory.create(name='In progress')
        status.name_fi = 'Käynnissä'  # type: ignore[attr-defined]
        status.save()

        panel = _bound_translations_panel(rf, status, data={'name': 'In progress', 'name_fi': 'x' * 500})

        assert panel.form.errors.get('name_fi')
        assert panel.is_open is True


def test_plan_edit_page_shows_translations_in_sections(plan, plan_admin_user, client):
    ClientPlanFactory.create(plan=plan)
    plan.other_languages = ['fi']
    plan.name_fi = 'Suunnitelma'  # type: ignore[attr-defined]
    plan.save()
    client.force_login(plan_admin_user)

    response = client.get(reverse(PlanViewSet().get_url_name('edit'), args=[plan.pk]))

    body = response.content.decode('utf-8')
    assert response.status_code == 200
    assert re.search(r'<summary class="translations-panel__summary">.*?Translations\s*</summary>', body, re.DOTALL)
    sections = {
        re.search(r'name="([^"]+)"', content).group(1): is_open  # type: ignore[union-attr]
        for is_open, content in re.findall(r'<details class="translations-panel"( open)?>(.*?)</details>', body, re.DOTALL)
    }
    # The plan name is translated, so its section starts folded; the short name is not, so it starts open.
    assert sections['name_fi'] == ''
    assert sections['short_name_fi'] == ' open'
    # Screen readers hear the field and the language; sighted users see only the language
    label = re.search(r'<label class="w-field__label" for="id_short_name_fi"[^>]*>(.*?)</label>', body, re.DOTALL)
    assert label is not None
    assert re.sub(r'\s+', ' ', label.group(1)).strip() == '<span class="w-sr-only">Short name: </span>Finnish'
