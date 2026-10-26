"""The submissions of a plan's actions to a report, as admins follow them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.urls import reverse
from django.utils.http import urlencode

if TYPE_CHECKING:
    from datetime import datetime

    from reversion.models import Revision

    from actions.models import Action

    from .models import Report


def user_can_submit_action(user, action: Action, report: Report) -> bool:
    """Return whether `user` may submit `action` to `report`, resubmit it or undo its submission."""
    if not user.can_modify_action(action):
        return False
    report_type = report.type
    if report_type.plan_id != action.plan_id:
        return False
    if report_type.only_plan_admins_can_mark_actions_as_complete:
        return user.is_general_admin_for_plan(action.plan)
    return True


@dataclass(frozen=True)
class ActionSubmission:
    """An action of a report's plan, and when and by whom it was submitted to the report, if it has been."""

    action: Action
    contact_persons: str
    responsible_parties: str
    submitted_at: datetime | None = None
    submitted_by: str | None = None
    undo_url: str | None = None


def _primary_names(related, is_primary, name) -> str:
    """Name the primary ones of an action's contact persons or responsible parties, or all if none is primary."""
    items = list(related.all())
    return ', '.join(name(item) for item in [item for item in items if is_primary(item)] or items)


def get_action_submissions(report: Report, return_url: str | None = None) -> list[ActionSubmission]:
    """
    Return the actions of the report's plan with their latest submission to it.

    With `return_url`, a submission of an open report can be undone, and the undo confirmation returns there.
    """
    from actions.models import ActionResponsibleParty

    latest_revisions: dict[int, Revision] = {}
    for snapshot in report.action_snapshots.select_related('action_version__revision__user'):
        revision = snapshot.action_version.revision
        action_id = int(snapshot.action_version.object_id)
        latest = latest_revisions.get(action_id)
        if latest is None or revision.date_created > latest.date_created:
            latest_revisions[action_id] = revision

    actions = report.type.plan.actions.prefetch_related('contact_persons__person', 'responsible_parties__organization')
    submissions: list[ActionSubmission] = []
    for action in actions:
        contact_persons = _primary_names(
            action.contact_persons, lambda contact: contact.primary_contact, lambda contact: str(contact.person)
        )
        responsible_parties = _primary_names(
            action.responsible_parties,
            lambda party: party.role == ActionResponsibleParty.Role.PRIMARY,
            lambda party: party.organization.name,
        )
        revision = latest_revisions.get(action.pk)
        if revision is None:
            submissions.append(
                ActionSubmission(action=action, contact_persons=contact_persons, responsible_parties=responsible_parties)
            )
            continue
        undo_url = None
        if return_url is not None and not report.is_complete:
            undo_url = reverse(
                'actions_action_modeladmin_undo_marking_action_as_complete',
                kwargs={'action_pk': action.pk, 'report_pk': report.pk},
            )
            undo_url = f'{undo_url}?{urlencode({"next": return_url})}'
        user = revision.user
        submissions.append(
            ActionSubmission(
                action=action,
                contact_persons=contact_persons,
                responsible_parties=responsible_parties,
                submitted_at=revision.date_created,
                submitted_by=(user.get_full_name() or user.email) if user is not None else None,
                undo_url=undo_url,
            )
        )
    return submissions
