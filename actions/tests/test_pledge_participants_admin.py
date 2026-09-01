from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

import pytest

from actions.models import PledgeCommitment, PublicUser
from actions.pledge_participants_admin import (
    ParticipantsViewSet,
    _get_participants_queryset,
    _opted_in_emails,
)
from actions.tests.factories import PlanFactory, PledgeFactory
from admin_site.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def active_plan(plan_admin_user):
    plan_obj = plan_admin_user.get_active_admin_plan()
    plan_obj.features.enable_community_engagement = True
    plan_obj.features.save()
    return plan_obj


def _make_participant(email: str, marketing: bool = False, client=None) -> PublicUser:
    now = timezone.now()
    return PublicUser.objects.create(
        email=email,
        client=client or ClientFactory.create(),
        terms_accepted_at=now,
        marketing_consented_at=now if marketing else None,
        email_verified_at=now,
    )


class TestParticipantsQueryset:
    def test_excludes_users_without_email(self, active_plan):
        pledge = PledgeFactory.create(plan=active_plan)
        anon = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge, public_user=anon)

        signed_up = _make_participant('alice@example.com')
        PledgeCommitment.objects.create(pledge=pledge, public_user=signed_up)

        result = list(_get_participants_queryset(active_plan))

        assert result == [signed_up]

    def test_only_signed_up_with_commitments_in_plan(self, active_plan):
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()

        own_pledge = PledgeFactory.create(plan=active_plan)
        other_pledge = PledgeFactory.create(plan=other_plan)

        in_plan = _make_participant('in@example.com')
        out_of_plan = _make_participant('out@example.com')
        _make_participant('lurker@example.com')  # no commitments

        PledgeCommitment.objects.create(pledge=own_pledge, public_user=in_plan)
        PledgeCommitment.objects.create(pledge=other_pledge, public_user=out_of_plan)

        result = list(_get_participants_queryset(active_plan).values_list('email', flat=True))

        assert result == ['in@example.com']

    def test_commitment_count_annotation_counts_per_plan(self, active_plan):
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        own_pledge_a = PledgeFactory.create(plan=active_plan)
        own_pledge_b = PledgeFactory.create(plan=active_plan)
        other_pledge = PledgeFactory.create(plan=other_plan)

        user = _make_participant('alice@example.com')
        PledgeCommitment.objects.create(pledge=own_pledge_a, public_user=user)
        PledgeCommitment.objects.create(pledge=own_pledge_b, public_user=user)
        PledgeCommitment.objects.create(pledge=other_pledge, public_user=user)

        row = _get_participants_queryset(active_plan).get(pk=user.pk)

        # commitment_count is a queryset annotation, not a model field, so mypy
        # doesn't know about it.
        assert getattr(row, 'commitment_count') == 2  # noqa: B009

    def test_pledge_scoped_queryset_counts_one(self, active_plan):
        a = PledgeFactory.create(plan=active_plan)
        b = PledgeFactory.create(plan=active_plan)
        user = _make_participant('alice@example.com')
        PledgeCommitment.objects.create(pledge=a, public_user=user)
        PledgeCommitment.objects.create(pledge=b, public_user=user)

        row = _get_participants_queryset(active_plan, pledge=a).get(pk=user.pk)

        assert getattr(row, 'commitment_count') == 1  # noqa: B009

    def test_pledge_scoped_queryset_rejects_pledge_from_other_plan(self, active_plan):
        # Defensive: if a caller passes a (plan, pledge) pair where the
        # pledge belongs to a different plan, the helper must return empty
        # rather than leak the other plan's participants.
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        other_pledge = PledgeFactory.create(plan=other_plan)
        user = _make_participant('alice@example.com')
        PledgeCommitment.objects.create(pledge=other_pledge, public_user=user)

        result = list(_get_participants_queryset(active_plan, pledge=other_pledge))

        assert result == []


class TestOptedInEmails:
    def test_returns_only_opted_in_sorted(self, active_plan):
        pledge = PledgeFactory.create(plan=active_plan)
        alice = _make_participant('alice@example.com', marketing=True)
        bob = _make_participant('bob@example.com', marketing=False)
        carol = _make_participant('carol@example.com', marketing=True)
        PledgeCommitment.objects.create(pledge=pledge, public_user=alice)
        PledgeCommitment.objects.create(pledge=pledge, public_user=bob)
        PledgeCommitment.objects.create(pledge=pledge, public_user=carol)

        assert _opted_in_emails(active_plan) == ['alice@example.com', 'carol@example.com']

    def test_pledge_scoped_excludes_other_pledges(self, active_plan):
        pledge_a = PledgeFactory.create(plan=active_plan)
        pledge_b = PledgeFactory.create(plan=active_plan)
        alice = _make_participant('alice@example.com', marketing=True)
        bob = _make_participant('bob@example.com', marketing=True)
        PledgeCommitment.objects.create(pledge=pledge_a, public_user=alice)
        PledgeCommitment.objects.create(pledge=pledge_b, public_user=bob)

        assert _opted_in_emails(active_plan, pledge=pledge_a) == ['alice@example.com']


class TestParticipantsIndexView:
    def _list_url(self) -> str:
        return reverse(ParticipantsViewSet().get_url_name('list'))

    def test_view_renders_for_plan_admin(self, client, plan_admin_user, active_plan):
        pledge = PledgeFactory.create(plan=active_plan)
        PledgeCommitment.objects.create(
            pledge=pledge,
            public_user=_make_participant('alice@example.com', marketing=True),
        )
        client.force_login(plan_admin_user)

        response = client.get(self._list_url())

        assert response.status_code == 200
        assert b'alice@example.com' in response.content

    def test_view_denied_for_action_contact_person(self, client, action_contact_person_user, active_plan):
        # Contact persons have admin access (is_staff) and may have an active
        # admin plan, but PublicUser.view is granted only via PLAN_ADMIN_PERMS
        # (actions/perms.py), not contact-person perms. The participants list
        # must enforce that distinction so contact persons can't read
        # participant emails for the plan.
        from actions.models import Action
        from actions.perms import add_contact_person_perms

        add_contact_person_perms(action_contact_person_user, Action)
        client.force_login(action_contact_person_user)

        response = client.get(self._list_url())

        assert response.status_code in (302, 403, 404)

    def test_view_denied_when_active_plan_is_not_admined(self, client, plan_admin_user, active_plan):
        # The user is a general plan admin for active_plan (Plan X), which
        # grants the global actions.view_publicuser Django permission. They
        # may also be a contact person for another plan (Plan Y) with
        # community engagement enabled. Switching the active admin plan to
        # Y must NOT expose Y's participants - the user isn't a general
        # admin there. The policy has to bind to the active plan, not just
        # the global model perm.
        from actions.models import Action
        from actions.perms import add_contact_person_perms

        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        other_action = other_plan.actions.first()
        if other_action is None:
            other_action = Action.objects.create(plan=other_plan, name='Other action')
        # Make plan_admin_user a contact person for other_plan's action; their
        # general-admin status for active_plan stays unchanged.
        plan_admin_user.person.contact_for_actions.add(other_action)
        add_contact_person_perms(plan_admin_user, Action)
        # Force the active admin plan to other_plan, where the user is only
        # a contact person.
        plan_admin_user.selected_admin_plan = other_plan
        plan_admin_user.save(update_fields=['selected_admin_plan'])
        client.force_login(plan_admin_user)

        response = client.get(self._list_url())

        assert response.status_code in (302, 403, 404)

    def test_view_hidden_when_feature_disabled(self, client, plan_admin_user, active_plan):
        active_plan.features.enable_community_engagement = False
        active_plan.features.save()
        client.force_login(plan_admin_user)

        response = client.get(self._list_url())

        # Wagtail's permission system returns 302 or 403 when denied; either is fine.
        assert response.status_code in (302, 403, 404)

    def test_sort_by_commitment_count(self, client, plan_admin_user, active_plan):
        many = PledgeFactory.create(plan=active_plan)
        few = PledgeFactory.create(plan=active_plan)
        alice = _make_participant('alice@example.com')
        bob = _make_participant('bob@example.com')
        PledgeCommitment.objects.create(pledge=many, public_user=alice)
        PledgeCommitment.objects.create(pledge=few, public_user=alice)
        PledgeCommitment.objects.create(pledge=many, public_user=bob)
        client.force_login(plan_admin_user)

        response = client.get(self._list_url() + '?' + urlencode({'ordering': '-commitment_count'}))

        assert response.status_code == 200
        body = response.content.decode('utf-8')
        assert body.index('alice@example.com') < body.index('bob@example.com')


class TestPledgeParticipantsPanel:
    def _make_bound_panel(self, request, pledge):
        from actions.models import Pledge
        from actions.pledge_participants_admin import PledgeParticipantsPanel

        panel = PledgeParticipantsPanel().bind_to_model(Pledge)
        return panel.get_bound_panel(instance=pledge, request=request, form=None)

    def test_panel_populated_for_plan_admin(self, rf, plan_admin_user, active_plan):
        pledge = PledgeFactory.create(plan=active_plan)
        PledgeCommitment.objects.create(
            pledge=pledge,
            public_user=_make_participant('alice@example.com', marketing=True),
        )
        request = rf.get('/admin/')
        request.user = plan_admin_user

        ctx = self._make_bound_panel(request, pledge).get_context_data()

        assert ctx['opted_in_emails'] == 'alice@example.com'
        assert len(ctx['participants']) == 1

    def test_panel_empty_when_active_plan_is_not_admined(self, rf, plan_admin_user, active_plan):
        # Mixed-role: plan_admin_user is a general admin of active_plan but
        # only a contact person on other_plan. The Pledge edit view itself is
        # gated more permissively, so the user can reach the edit page for an
        # other_plan pledge - but the participants tab must not embed the
        # plan's opted-in emails.
        from actions.models import Action
        from actions.perms import add_contact_person_perms

        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        other_pledge = PledgeFactory.create(plan=other_plan)
        PledgeCommitment.objects.create(
            pledge=other_pledge,
            public_user=_make_participant('bob@example.com', marketing=True),
        )
        other_action = other_plan.actions.first()
        if other_action is None:
            other_action = Action.objects.create(plan=other_plan, name='Other action')
        plan_admin_user.person.contact_for_actions.add(other_action)
        add_contact_person_perms(plan_admin_user, Action)
        plan_admin_user.selected_admin_plan = other_plan
        plan_admin_user.save(update_fields=['selected_admin_plan'])
        # The fixture-cached User has stale perms and adminable_plans caches;
        # refetch to start fresh so the contact-person assignment registers.
        plan_admin_user = type(plan_admin_user).objects.get(pk=plan_admin_user.pk)
        request = rf.get('/admin/')
        request.user = plan_admin_user

        ctx = self._make_bound_panel(request, other_pledge).get_context_data()

        assert ctx['opted_in_emails'] == ''
        assert ctx['participants'] == []
        assert ctx['export_url'] is None


class TestCsvExportEndpoint:
    def test_global_csv_contains_only_opted_in_emails(self, client, plan_admin_user, active_plan):
        pledge = PledgeFactory.create(plan=active_plan)
        alice = _make_participant('alice@example.com', marketing=True)
        bob = _make_participant('bob@example.com', marketing=False)
        PledgeCommitment.objects.create(pledge=pledge, public_user=alice)
        PledgeCommitment.objects.create(pledge=pledge, public_user=bob)
        client.force_login(plan_admin_user)

        response = client.get(reverse('pledge_participants_export_csv'))

        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv'
        body = response.content.decode('utf-8')
        assert 'alice@example.com' in body
        assert 'bob@example.com' not in body

    def test_per_pledge_csv_scoped_to_pledge(self, client, plan_admin_user, active_plan):
        pledge_a = PledgeFactory.create(plan=active_plan)
        pledge_b = PledgeFactory.create(plan=active_plan)
        alice = _make_participant('alice@example.com', marketing=True)
        carol = _make_participant('carol@example.com', marketing=True)
        PledgeCommitment.objects.create(pledge=pledge_a, public_user=alice)
        PledgeCommitment.objects.create(pledge=pledge_b, public_user=carol)
        client.force_login(plan_admin_user)

        response = client.get(
            reverse('pledge_participants_export_csv_for_pledge', args=[pledge_a.pk]),
        )

        assert response.status_code == 200
        body = response.content.decode('utf-8')
        assert 'alice@example.com' in body
        assert 'carol@example.com' not in body

    def test_per_pledge_csv_rejects_pledge_outside_active_plan(self, client, plan_admin_user, active_plan):
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        other_pledge = PledgeFactory.create(plan=other_plan)
        client.force_login(plan_admin_user)

        response = client.get(
            reverse('pledge_participants_export_csv_for_pledge', args=[other_pledge.pk]),
        )

        # Wagtail admin URLs raise PermissionDenied as a 302 redirect to the
        # admin home; either explicit 403 or that redirect is "denied".
        assert response.status_code in (302, 403)

    def test_csv_unauthenticated_redirects(self, client):
        response = client.get(reverse('pledge_participants_export_csv'))
        # Wagtail admin auth redirects to login (302) or denies (403)
        assert response.status_code in (302, 403)

    def test_csv_anonymous_users_excluded(self, client, plan_admin_user, active_plan):
        pledge = PledgeFactory.create(plan=active_plan)
        # Anonymous user with a commitment - shouldn't appear since no email
        anon = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge, public_user=anon)
        client.force_login(plan_admin_user)

        response = client.get(reverse('pledge_participants_export_csv'))

        assert response.status_code == 200
        body = response.content.decode('utf-8')
        assert body.strip() == ''  # no opted-in users
