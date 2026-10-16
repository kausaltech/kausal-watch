from __future__ import annotations

from django.urls import reverse

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


@pytest.fixture
def copy_url(plan):
    return reverse('actions_plan_modeladmin_copy', kwargs={'instance_pk': plan.pk})


@pytest.mark.django_db
@pytest.mark.parametrize('method', ['get', 'post'])
def test_plan_copy_view_denies_plan_admins(client, plan_admin_user, copy_url, method, monkeypatch):
    queued = []
    monkeypatch.setattr('copying.views.copy_plan.delay_on_commit', lambda **kwargs: queued.append(kwargs))
    client.force_login(plan_admin_user)
    response = getattr(client, method)(copy_url, {'identifier': 'copy', 'name': 'Copy', 'supersede_original_plan': 'on'})
    # Wagtail redirects to the dashboard if permission is denied
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')
    assert not queued


@pytest.mark.django_db
def test_plan_copy_view_queues_copy_for_superusers(client, superuser, plan, copy_url, monkeypatch):
    queued = []
    monkeypatch.setattr('copying.views.copy_plan.delay_on_commit', lambda **kwargs: queued.append(kwargs))
    client.force_login(superuser)
    assert client.get(copy_url).status_code == 200
    response = client.post(copy_url, {'identifier': 'copy', 'name': 'Copy'})
    assert response.status_code == 302
    assert [str(kwargs['plan_id']) for kwargs in queued] == [str(plan.pk)]
