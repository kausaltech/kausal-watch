"""
Tests for the columns of the person listing in the admin.

Rendering the whole index page needs a built staticfiles manifest, so the list display callables
are exercised directly against the queryset the listing uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from people.tests.factories import PersonFactory
from people.wagtail_admin import PersonAdmin

if TYPE_CHECKING:
    from django.test.client import RequestFactory

    from actions.models import Plan
    from people.models import Person
    from users.models import User

pytestmark = pytest.mark.django_db


def get_cell(rf: RequestFactory, user: User, person: Person, column: str, **params: str) -> Any:
    request = rf.get('/', params)
    request.user = user
    person_admin = PersonAdmin()
    listed = person_admin.get_queryset(request).get(pk=person.pk)
    fields = {getattr(f, '__name__', f): f for f in person_admin.get_list_display(request)}
    return fields[column](listed)


def test_person_without_name_is_listed_by_email(rf: RequestFactory, plan: Plan, plan_admin_user: User):
    person = PersonFactory.create(first_name='', last_name='', email='nameless@example.com', organization=plan.organization)
    assert 'nameless@example.com' in get_cell(rf, plan_admin_user, person, 'first_name')


def test_person_with_name_is_not_listed_by_email(rf: RequestFactory, plan: Plan, plan_admin_user: User):
    person = PersonFactory.create(first_name='Named', last_name='', email='named@example.com', organization=plan.organization)
    cell = get_cell(rf, plan_admin_user, person, 'first_name')
    assert 'Named' in cell
    assert 'named@example.com' not in cell
