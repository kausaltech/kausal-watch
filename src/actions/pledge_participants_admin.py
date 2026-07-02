"""
Admin UIs surfacing PublicUsers who have committed to pledges.

Two surfaces:
- Global list (ParticipantsViewSet): every signed-up PublicUser with at
  least one commitment in the active admin plan's pledges.
- Per-pledge tab (PledgeParticipantsPanel): the same list scoped to a
  single Pledge, rendered as a tab on the pledge edit view.

Both expose a CSV export and a copy-to-clipboard button that only emit
emails of participants who have opted in to marketing.
"""

from __future__ import annotations

import csv
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from wagtail.admin.panels import Panel
from wagtail.admin.ui.tables import BooleanColumn, Column
from wagtail.admin.views.mixins import Echo
from wagtail.snippets.models import register_snippet

from kausal_common.users import user_or_bust

from admin_site.permissions import PlanRelatedPermissionPolicy
from admin_site.viewsets import WatchIndexView, WatchViewSet
from users.models import User

from .models import Pledge
from .models.pledge import PublicUser

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.db.models import QuerySet
    from django.http import HttpRequest

    from actions.models.plan import Plan


def _get_participants_queryset(plan: Plan, pledge: Pledge | None = None) -> QuerySet[PublicUser]:
    """
    Return signed-up PublicUsers with >=1 commitment in the plan.

    Annotated with `commitment_count` (commitments in this plan; or to the
    specific pledge when `pledge` is given) and `has_marketing_consent`
    (bool, surfaced as a tick column).
    """
    commitment_filter = Q(commitments__pledge__plan=plan)
    if pledge is not None:
        # AND with the plan predicate (don't replace it) so mismatched
        # (plan, pledge) pairs return empty instead of leaking another
        # plan's participants. Commitments are stored against the primary
        # translation; resolve to that so the count is consistent
        # regardless of which translation the caller passed in.
        commitment_filter &= Q(commitments__pledge=pledge.get_primary_translation())
    return (
        PublicUser.objects
        .exclude(email__isnull=True)
        .exclude(email='')
        .filter(commitment_filter)
        .annotate(
            commitment_count=Count(
                'commitments',
                filter=commitment_filter,
                distinct=True,
            ),
        )
        .filter(commitment_count__gt=0)
        .distinct()
    )


def _opted_in_emails(plan: Plan, pledge: Pledge | None = None) -> list[str]:
    """Return emails of participants who have opted in to marketing, sorted."""
    qs = _get_participants_queryset(plan, pledge).filter(marketing_consented_at__isnull=False).exclude(email__isnull=True)
    return sorted(email for email in qs.values_list('email', flat=True) if email)


class ParticipantsPermissionPolicy(PlanRelatedPermissionPolicy):
    """
    Read-only for plan admins on plans that have community engagement enabled.

    Mirrors PledgePermissionPolicy's gating; the Participants UI is only
    meaningful when the underlying Pledge feature is enabled.
    """

    def user_has_permission(self, user: AbstractBaseUser | AnonymousUser, action: str) -> bool:
        if not super().user_has_permission(user, action):
            return False
        if not isinstance(user, User):
            return False
        plan = user.get_active_admin_plan(required=False)
        if plan is None:
            return False
        if not user.is_general_admin_for_plan(plan):
            return False
        if not plan.features.enable_community_engagement:
            return False
        return action == 'view'

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, a) for a in actions)


class ParticipantsIndexView(WatchIndexView[PublicUser]):
    """List of signed-up PublicUsers committed to pledges in the active plan."""

    page_title = _('Pledge participants')
    show_export_buttons = False  # we provide a tailored CSV button below
    list_export: list[str] = []  # Wagtail's auto-export off; CSV is via the custom button

    @cached_property
    def columns(self):  # type: ignore[override]
        # Bulk actions aren't available for now
        return [column for column in super().columns if column.name != 'bulk_actions']

    def get_queryset(self) -> QuerySet[PublicUser]:
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        qs = _get_participants_queryset(plan)
        # Honor sort param ('email', '-email', 'commitment_count', etc).
        ordering = self.request.GET.get('ordering')
        sortable = {'email', 'commitment_count', 'marketing_consented_at'}
        if ordering and ordering.lstrip('-') in sortable:
            return qs.order_by(ordering)
        return qs.order_by('email')

    def get_header_more_buttons(self):
        from wagtail.admin.widgets.button import Button

        buttons = list(super().get_header_more_buttons())
        export_url = reverse('pledge_participants_export_csv')
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        emails = ', '.join(_opted_in_emails(plan))
        buttons.append(
            Button(
                _('Copy opted-in emails'),
                url='#',
                icon_name='copy',
                priority=89,
                attrs={
                    'data-pledge-participants-emails': emails,
                    'data-pledge-participants-copied-label': str(_('Copied')),
                },
            ),
        )
        buttons.append(
            Button(
                _('Export opted-in emails as CSV'),
                url=export_url,
                icon_name='download',
                priority=90,
            ),
        )
        return sorted(buttons)


class ParticipantsViewSet(WatchViewSet[PublicUser]):
    """Read-only admin viewset for PublicUsers committed to plan pledges."""

    model = PublicUser
    name = 'pledge_participants'
    icon = 'group'
    menu_label = _('Participants')
    menu_icon = 'group'
    add_to_admin_menu = False  # menu wired via custom Pledges submenu
    menu_item_is_registered = True
    list_display = [
        Column('email', label=_('Email'), sort_key='email'),
        Column('commitment_count', label=_('Pledges committed'), sort_key='commitment_count'),
        BooleanColumn(
            'has_marketing_consent',
            label=_('Marketing opt-in'),
            sort_key='marketing_consented_at',
        ),
    ]
    index_view_class = ParticipantsIndexView  # type: ignore[assignment]
    inspect_view_enabled = False
    copy_view_enabled = False

    @property
    def permission_policy(self):
        return ParticipantsPermissionPolicy(self.model)

    def get_urlpatterns(self):
        # SnippetViewSet hard-codes add/edit/delete routes even when the
        # view classes are set to None. Override to expose only listing
        # endpoints; this ViewSet is read-only.
        return [
            path('', self.index_view, name='list'),
            path('results/', self.index_results_view, name='list_results'),
        ]


# Wagtail's BooleanColumn reads bool() of the attribute. PublicUser.marketing_consented_at
# is a datetime-or-None; bool(datetime) is True, bool(None) is False, so the column
# already does the right thing as long as we expose `has_marketing_consent` as a property.
def _has_marketing_consent(self: PublicUser) -> bool:
    return self.marketing_consented_at is not None


PublicUser.has_marketing_consent = property(_has_marketing_consent)  # type: ignore[attr-defined]


class _ParticipantsCsvView(View):
    """CSV download: one opted-in email per line."""

    pledge_id: int | None = None

    def _check_permission(self, request: HttpRequest, plan: Plan) -> None:
        user = request.user
        if not isinstance(user, User):
            raise PermissionDenied
        if not user.is_general_admin_for_plan(plan):
            raise PermissionDenied
        if not plan.features.enable_community_engagement:
            raise PermissionDenied

    def get(self, request: HttpRequest, *, pledge_id: int | None = None) -> HttpResponse:
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        self._check_permission(request, plan)

        pledge: Pledge | None = None
        if pledge_id is not None:
            pledge = Pledge.objects.filter(pk=pledge_id, plan=plan).first()
            if pledge is None:
                raise PermissionDenied
            filename = f'pledge-{pledge.slug}-opted-in-emails.csv'
        else:
            filename = f'pledge-participants-opted-in-emails-{plan.identifier}.csv'

        emails = _opted_in_emails(plan, pledge)

        def _stream() -> Any:
            writer = csv.writer(Echo())
            for email in emails:
                yield writer.writerow([email])

        response = HttpResponse(_stream(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


def participants_csv_view(request: HttpRequest) -> HttpResponse:
    return cast('HttpResponse', _ParticipantsCsvView.as_view()(request))


def pledge_participants_csv_view(request: HttpRequest, pledge_id: int) -> HttpResponse:
    return cast('HttpResponse', _ParticipantsCsvView.as_view()(request, pledge_id=pledge_id))


class PledgeParticipantsPanel(Panel):
    """
    Tab on the pledge edit view listing participants for that pledge.

    Renders inert (not a form field): table of email + opt-in column, plus
    'Copy opted-in emails' and 'Export' buttons. The opted-in email list
    is embedded as a hidden data attribute so the copy button can read it
    without a round-trip.
    """

    heading = _('Participants')

    class BoundPanel(Panel.BoundPanel):
        template_name = 'admin_site/pledge_participants_panel.html'

        def get_context_data(self, parent_context=None):
            ctx = super().get_context_data(parent_context) or {}
            ctx['participants'] = []
            ctx['opted_in_emails'] = ''
            ctx['export_url'] = None
            ctx['copy_emails_label'] = _('Copy opted-in emails')

            pledge: Pledge | None = cast('Pledge | None', self.instance)
            if pledge is None or pledge.pk is None:
                return ctx
            user = user_or_bust(self.request.user) if self.request else None
            plan = user.get_active_admin_plan() if user is not None else None
            # PledgePermissionPolicy lets the user open the edit view if they
            # have the global change_pledge perm and the pledge belongs to
            # their active plan, but that doesn't guarantee they're a general
            # admin there. Mirror the CSV endpoint and the global Participants
            # list: tab populates only when the user actually admins this plan.
            if plan is None or user is None or not user.is_general_admin_for_plan(plan):
                return ctx
            participants = list(
                _get_participants_queryset(plan, pledge).order_by('email').values('email', 'marketing_consented_at')
            )
            ctx['participants'] = participants
            ctx['opted_in_emails'] = ', '.join(_opted_in_emails(plan, pledge))
            ctx['export_url'] = reverse('pledge_participants_export_csv_for_pledge', args=[pledge.pk])
            return ctx


def get_pledge_participants_admin_urlpatterns() -> list[Any]:
    """URL patterns for the CSV export endpoints, registered via wagtail hook."""
    return [
        path('pledge-participants/export.csv', participants_csv_view, name='pledge_participants_export_csv'),
        path(
            'pledge-participants/<int:pledge_id>/export.csv',
            pledge_participants_csv_view,
            name='pledge_participants_export_csv_for_pledge',
        ),
    ]


register_snippet(ParticipantsViewSet)
