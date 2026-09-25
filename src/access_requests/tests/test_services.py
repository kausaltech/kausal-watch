from __future__ import annotations

import pytest

from access_requests.models import AccessRequest
from access_requests.services import (
    AccessRequestNotPendingError,
    approve_access_request,
    create_access_request,
    reject_access_request,
)
from access_requests.tests.factories import AccessRequestFactory
from actions.models import PlanPublicSiteViewer
from actions.tests.factories import PlanFactory
from people.models import Person
from people.tests.factories import PersonFactory
from users.models import User
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestCreate:
    def test_creates_pending_request_with_normalised_email(self):
        plan = PlanFactory.create()
        create_access_request(plan, '  Visitor@Example.COM ', first_name='Vera', last_name='Visitor')
        req = AccessRequest.objects.get()
        assert req.plan == plan
        assert req.email == 'visitor@example.com'
        assert (req.first_name, req.last_name) == ('Vera', 'Visitor')
        assert req.status == AccessRequest.Status.PENDING

    def test_pending_request_is_kept_as_is(self):
        plan = PlanFactory.create()
        existing = AccessRequestFactory.create(plan=plan, email='visitor@example.com')
        create_access_request(plan, 'VISITOR@example.com', first_name='New', last_name='Name')
        assert list(AccessRequest.objects.all()) == [existing]
        existing.refresh_from_db()
        assert existing.first_name == ''

    def test_rejected_visitor_gets_a_new_request(self):
        plan = PlanFactory.create()
        AccessRequestFactory.create(plan=plan, email='visitor@example.com', status=AccessRequest.Status.REJECTED)
        create_access_request(plan, 'visitor@example.com')
        assert AccessRequest.objects.qs.pending().filter(plan=plan).count() == 1

    def test_no_request_when_user_can_already_view_the_plan(self):
        plan = PlanFactory.create()
        person = PersonFactory.create(email='viewer@example.com')
        PlanPublicSiteViewer.objects.create(plan=plan, person=person)
        create_access_request(plan, 'viewer@example.com')
        assert not AccessRequest.objects.exists()

    def test_viewer_of_another_plan_may_request(self):
        plan = PlanFactory.create()
        person = PersonFactory.create(email='viewer@example.com')
        PlanPublicSiteViewer.objects.create(plan=PlanFactory.create(), person=person)
        create_access_request(plan, 'viewer@example.com')
        assert AccessRequest.objects.filter(plan=plan).exists()


class TestApprove:
    def test_creates_person_user_and_viewer_grant_only(self):
        plan = PlanFactory.create()
        admin = UserFactory.create()
        req = AccessRequestFactory.create(plan=plan, email='visitor@example.com', first_name='Vera', last_name='Visitor')

        approve_access_request(req, by=admin)

        req.refresh_from_db()
        assert req.status == AccessRequest.Status.APPROVED
        assert req.decided_by == admin
        assert req.decided_at is not None
        person = Person.objects.get(email='visitor@example.com')
        assert req.person == person
        assert (person.first_name, person.last_name) == ('Vera', 'Visitor')
        assert person.organization == plan.organization
        assert PlanPublicSiteViewer.objects.filter(plan=plan, person=person).exists()
        user = User.objects.get(email='visitor@example.com')
        assert user.can_access_public_site(plan)
        assert not user.can_access_admin(plan)

    def test_reuses_existing_person(self):
        plan = PlanFactory.create()
        person = PersonFactory.create(email='Visitor@example.com')
        req = AccessRequestFactory.create(plan=plan, email='visitor@example.com')

        approve_access_request(req, by=UserFactory.create())

        assert Person.objects.filter(email__iexact='visitor@example.com').count() == 1
        req.refresh_from_db()
        assert req.person == person
        assert PlanPublicSiteViewer.objects.filter(plan=plan, person=person).exists()

    def test_existing_admin_gets_no_viewer_grant(self):
        # A viewer row marks a person as "public site only" in the person form, which would hide
        # the admin rights they already have.
        plan = PlanFactory.create()
        person = PersonFactory.create(email='admin@example.com', general_admin_plans=[plan])
        req = AccessRequestFactory.create(plan=plan, email='admin@example.com')

        approve_access_request(req, by=UserFactory.create())

        assert not PlanPublicSiteViewer.objects.filter(plan=plan, person=person).exists()
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.APPROVED

    @pytest.mark.parametrize('status', [AccessRequest.Status.APPROVED, AccessRequest.Status.REJECTED])
    def test_refuses_a_request_that_is_not_pending(self, status):
        req = AccessRequestFactory.create(status=status)
        with pytest.raises(AccessRequestNotPendingError):
            approve_access_request(req, by=UserFactory.create())
        assert not Person.objects.filter(email=req.email).exists()


class TestReject:
    def test_marks_request_rejected(self):
        admin = UserFactory.create()
        req = AccessRequestFactory.create()

        reject_access_request(req, by=admin)

        req.refresh_from_db()
        assert req.status == AccessRequest.Status.REJECTED
        assert req.decided_by == admin
        assert req.decided_at is not None
        assert not Person.objects.filter(email=req.email).exists()

    def test_refuses_a_request_that_is_not_pending(self):
        req = AccessRequestFactory.create(status=AccessRequest.Status.APPROVED)
        with pytest.raises(AccessRequestNotPendingError):
            reject_access_request(req, by=UserFactory.create())

    def test_uses_the_current_state_not_a_stale_instance(self):
        # Two admins acting on the same row from different tabs: the second one sees the first decision.
        req = AccessRequestFactory.create()
        stale = AccessRequest.objects.get(pk=req.pk)
        approve_access_request(req, by=UserFactory.create())
        with pytest.raises(AccessRequestNotPendingError):
            reject_access_request(stale, by=UserFactory.create())
