import pytest

from actions.models.category import CommonCategoryType
from admin_site.wagtail import diff_common_category_types

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
