from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from aplans.utils import PlanRelatedModel

from actions.models.plan import Plan
from audit_logging.utils import BulkActionModelList
from pages.models import AplansPage

from .models import PlanScopedModelLogEntry, PlanScopedPageLogEntry


@hooks.register("register_log_actions")
def register_core_log_actions(actions):
    actions.register_model(Plan, PlanScopedModelLogEntry)
    actions.register_model(PlanRelatedModel, PlanScopedModelLogEntry)
    actions.register_model(BulkActionModelList, PlanScopedModelLogEntry)
    actions.register_model(AplansPage, PlanScopedPageLogEntry)


@hooks.register('register_admin_menu_item')
def register_audit_log():
    return MenuItem(
        pgettext_lazy('menu item for accessing history of changes', 'Change history'),
        reverse('watch-plan-history'),
        icon_name='history',
        order=10000,
    )
