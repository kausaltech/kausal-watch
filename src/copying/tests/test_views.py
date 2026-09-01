from __future__ import annotations

import pytest


def test_plan_copy_view_accepts_as_view_kwargs():
    """
    as_view() must accept all kwargs that are passed when the view is used.

    Django's View.as_view() checks hasattr(cls, key) for each kwarg.
    Type annotations without default values do NOT create class attributes,
    so they will cause TypeError if passed as kwargs to as_view().

    This test ensures that PlanCopyView.plan_id has a default value
    (or is otherwise a class attribute) so it can be passed to as_view().

    This is a preventive test - PlanCopyView currently has a default value,
    but this test will catch regressions if someone removes it during refactoring.
    """
    from copying.views import PlanCopyView

    # Verify the class attribute exists
    assert hasattr(PlanCopyView, 'plan_id'), 'PlanCopyView must have plan_id as a class attribute'

    # Verify as_view() accepts the kwarg (passed in actions/wagtail_admin.py:273)
    try:
        PlanCopyView.as_view(plan_id=123)
    except TypeError as e:
        if 'invalid keyword' in str(e):
            pytest.fail(f'as_view() rejected a keyword argument: {e}')
        raise
