from __future__ import annotations

from typing import TYPE_CHECKING, override

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from kausal_common.users import user_or_none

from aplans.utils import PlanRelatedModel

from actions.models.plan import Plan
from pages.models import AplansPage

from .models import PlanScopedModelLogEntry, PlanScopedPageLogEntry

if TYPE_CHECKING:
    from aplans.types import WatchAdminRequest


@hooks.register("register_log_actions")
def register_core_log_actions(actions):
    actions.register_model(Plan, PlanScopedModelLogEntry)
    actions.register_model(PlanRelatedModel, PlanScopedModelLogEntry)
    actions.register_model(AplansPage, PlanScopedPageLogEntry)


@hooks.register('register_admin_menu_item')
def register_audit_log():
    return MenuItem(
        _('Audit log'),
        reverse('watch-plan-history'),
        icon_name='history',
        order=10000,
    )
