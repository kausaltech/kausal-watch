from django.forms import modelform_factory
from django.http import HttpResponse

import pytest

from actions.models import Plan
from actions.models.category import CategoryType, CommonCategoryType
from actions.tests.factories import CategoryTypeFactory, CommonCategoryTypeFactory
from actions.wagtail_admin import PlanAdmin, PlanEditView
from admin_site.wagtail import AplansEditView, diff_common_category_types

pytestmark = pytest.mark.django_db


def test_diff_with_no_new_common_category_types(plan, common_category_type_factory):
    """
    An empty selection must not be turned into a set operation on an empty queryset.

    A `pk__in=[]` operand makes Django emit an `EXCEPT` with a nested `ORDER BY`,
    which PostgreSQL rejects.
    """
    cct = common_category_type_factory()
    plan.common_category_types.add(cct)
    new = CommonCategoryType.objects.filter(pk__in=[])

    added, removed = diff_common_category_types(plan.common_category_types.all(), new)

    assert added == []
    assert removed == [cct]


def test_diff_reports_added_and_removed(plan, common_category_type_factory):
    kept = common_category_type_factory()
    removed_cct = common_category_type_factory()
    added_cct = common_category_type_factory()
    plan.common_category_types.set([kept, removed_cct])
    new = CommonCategoryType.objects.filter(pk__in=[kept.pk, added_cct.pk])

    added, removed = diff_common_category_types(plan.common_category_types.all(), new)

    assert added == [added_cct]
    assert removed == [removed_cct]


def test_plan_edit_clears_common_category_types(plan, monkeypatch):
    common_category_type = CommonCategoryTypeFactory.create()
    category_type = CategoryTypeFactory.create(plan=plan, common=common_category_type)
    plan.common_category_types.add(common_category_type)
    form_class = modelform_factory(Plan, fields=('common_category_types',))
    form = form_class(data={'common_category_types': []}, instance=plan)
    assert form.is_valid()
    expected_response = HttpResponse()

    def save_form(_view, form):
        form.save()
        return expected_response

    monkeypatch.setattr(AplansEditView, 'form_valid', save_form)
    view = PlanEditView(PlanAdmin(), str(plan.pk))

    response = view.form_valid(form)

    assert response is expected_response
    assert not plan.common_category_types.exists()
    assert not CategoryType.objects.filter(pk=category_type.pk).exists()
