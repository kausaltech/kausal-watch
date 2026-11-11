"""How the Wagtail admin saves actions, depending on whether the plan moderates them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail.actions.create import CreateAction
from wagtail.actions.edit import EditAction

if TYPE_CHECKING:
    from actions.models import Action


class ActionCreateAction(CreateAction):
    """Save a new action as it is; only later edits are held back as drafts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.draftstate_enabled = False


class ActionEditAction(EditAction):
    """
    Save an action directly, or as a draft if its plan has a moderation workflow.

    Without moderation the form writes to the database and `Action.save_revision()` publishes the
    revision. With moderation only the revision is written, also for an action that is not live.
    """

    instance: Action

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.draftstate_enabled = self.instance.plan.features.enable_moderation_workflow

    def _save_instance(self) -> None:
        if not self.draftstate_enabled or self.form is None:
            super()._save_instance()
            return
        self.instance = self.form.save(commit=False)
