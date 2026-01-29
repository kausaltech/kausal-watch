from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import IntegerField, Value
from django.forms import CheckboxSelectMultiple
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from wagtail.admin.filters import ContentTypeFilter, MultipleUserFilter
from wagtail.admin.views.reports.audit_logging import (
    LogEntriesView,
    SiteHistoryReportFilterSet,
    get_content_types_for_filter,
)
from wagtail.log_actions import registry as log_action_registry
from wagtail.models import ModelLogEntry, PageLogEntry
from wagtail.permissions import ModelPermissionPolicy

import django_filters

from audit_logging.models import PlanScopedModelLogEntry

LOG_MODELS_TO_EXCLUDE = (ModelLogEntry, PageLogEntry)


class CustomSiteHistoryReportFilterSet(SiteHistoryReportFilterSet):
    """Subclassed simply to change terminology."""

    action = django_filters.MultipleChoiceFilter(
        label=pgettext_lazy('type of change (e.g., "create", "edit" or "delete")', 'Change'),
        widget=CheckboxSelectMultiple,
    )
    user = MultipleUserFilter(
        label=_('Changed by'),
        widget=CheckboxSelectMultiple,
    )
    object_type = ContentTypeFilter(
        label=_('Item type'),
        method='filter_object_type',
        queryset=lambda request: get_content_types_for_filter(request.user),
    )

    def get_users_queryset(self):
        """
        Get users who have made changes in the log models we actually display.

        This must iterate through the same log models as get_filtered_queryset()
        to avoid showing users in the filter who have no matching log entries.

        Since items can be shared between plans, we show all users who have
        entries in the displayed log models, without plan-specific filtering.
        """
        # Collect user IDs from only the log models we want to display
        user_ids = set()
        for log_model in log_action_registry.get_log_entry_models():
            if log_model not in LOG_MODELS_TO_EXCLUDE:
                user_ids.update(
                    log_model.objects.viewable_by_user(self.request.user).get_user_ids()
                )

        User = get_user_model()
        return User.objects.filter(pk__in=user_ids).order_by(User.USERNAME_FIELD)


class PlanScopedLogEntriesView(LogEntriesView):
    results_template_name = "site_history_results.html"
    page_title = pgettext_lazy("page title for history of changes", "Change history")
    permission_policy: ModelPermissionPolicy = ModelPermissionPolicy(PlanScopedModelLogEntry)
    filterset_class = CustomSiteHistoryReportFilterSet
    permission_required = 'view'

    def get_log_models(self):
        """
        Return the list of log entry models to display, excluding unwanted models.

        This is used by both get_filtered_queryset() and indirectly by the
        filterset's get_users_queryset() to ensure consistency.
        """
        all_models = list(log_action_registry.get_log_entry_models())
        return [model for model in all_models if model not in LOG_MODELS_TO_EXCLUDE]

    def get_filtered_queryset(self):
        """
        Override to exclude certain log models from the union query.

        This is a copy of the parent implementation with one key change:
        we use get_log_models() instead of getting all registered models.

        This ensures that:
        1. Only desired log entries appear in the results
        2. The filterset's user filter matches the actual displayed entries
        """
        queryset = None

        # CUSTOMIZATION: Use filtered list instead of all registered models
        self.log_models = self.get_log_models()

        # Rest is identical to parent implementation
        for log_model_index, log_model in enumerate(self.log_models):
            sub_queryset = (
                log_model.objects.viewable_by_user(self.request.user)
                .values("pk", "timestamp")
                .annotate(
                    log_model_index=Value(log_model_index, output_field=IntegerField())
                )
            )
            sub_queryset = self.filter_queryset(sub_queryset)
            sub_queryset = sub_queryset.order_by()
            if queryset is None:
                queryset = sub_queryset
            else:
                queryset = queryset.union(sub_queryset)

        if queryset is None:
            return None
        return queryset.order_by("-timestamp")
