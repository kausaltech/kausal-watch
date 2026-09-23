"""
Tests for changing a plan's visibility in the admin.

Publishing opens a plan up and unpublishing deliberately leaves it open, so the plan edit form is
the one place visibility can be narrowed again. It is superuser-only, like the flag it replaced:
who may read a plan is not a choice a plan's own admins make.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import RestrictedVisibilityModel

from actions.models import Plan
from actions.tests.factories import CategoryTypeFactory
from actions.wagtail_admin import PlanAdmin
from admin_site.tests.factories import ClientPlanFactory

if TYPE_CHECKING:
    from django.forms import BaseFormSet, Form

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC


def _edit_form(rf, user, plan: Plan, data: dict[str, Any] | None = None):
    request = rf.get('/')
    request.user = user
    with ctx_request.activate(request), ctx_instance.activate(plan):
        form_class = PlanAdmin().get_edit_handler().bind_to_model(Plan).get_form_class()
        return form_class(data=data, instance=plan, for_user=user)


def _post_data(form: Form) -> dict[str, Any]:
    """Flatten an unbound form, formsets included, into the data that submitting it unchanged would post."""
    data: dict[str, Any] = {}

    def add(form: Form) -> None:
        for bound_field in form:
            value = bound_field.value()
            if value is None or value is False:
                continue
            data[bound_field.html_name] = value

    add(form)
    formsets: dict[str, BaseFormSet] = getattr(form, 'formsets', {})
    for formset in formsets.values():
        add(formset.management_form)
        for child in formset.forms:
            add(child)
    return data


class TestVisibilityPanel:
    def test_a_superuser_can_set_visibility(self, rf, superuser, plan_factory):
        form = _edit_form(rf, superuser, plan_factory())
        assert 'visibility' in form.fields

    def test_a_plan_admin_cannot(self, rf, plan_factory, person_factory):
        plan = plan_factory()
        admin = person_factory(general_admin_plans=[plan]).user
        form = _edit_form(rf, admin, plan)
        assert 'visibility' not in form.fields

    @pytest.mark.parametrize(('before', 'after'), [(PUBLIC, INTERNAL), (INTERNAL, PUBLIC)])
    def test_submitting_the_form_changes_visibility(self, rf, superuser, plan_factory, before, after):
        """
        Narrowing a public plan back to internal is the transition nothing else in the admin offers.

        The form is validated but not saved: saving a plan also renames its site, root pages and
        groups, which leaves stale entries in the process-wide cache once the test's transaction
        rolls back. Validation is where the form writes the submitted value onto the plan.
        """
        plan = plan_factory(visibility=before)
        # The form requires both, as every real plan has them.
        ClientPlanFactory.create(plan=plan, is_primary=True)
        plan.primary_action_classification = CategoryTypeFactory.create(plan=plan)
        plan.save(update_fields=['primary_action_classification'])
        data = _post_data(_edit_form(rf, superuser, plan))
        data['visibility'] = after

        form = _edit_form(rf, superuser, plan, data=data)
        assert form.is_valid(), form.errors
        assert form.instance.visibility == after
