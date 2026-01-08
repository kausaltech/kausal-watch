from __future__ import annotations

from django.db.models import Q
from django.forms import CheckboxSelectMultiple
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from wagtail.admin.filters import ContentTypeFilter, MultipleUserFilter
from wagtail.admin.views.reports.audit_logging import (
    LogEntriesView,
    SiteHistoryReportFilterSet,
    get_content_types_for_filter,
)
from wagtail.models import ModelLogEntry, PageLogEntry
from wagtail.permissions import ModelPermissionPolicy

import django_filters

from audit_logging.models import PlanScopedModelLogEntry
from people.models import Person


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
        plan = self.request.user.get_active_admin_plan()
        qs = super().get_users_queryset()
        if not plan:
            return qs.none()
        persons_available_for_plan = Person.objects.available_for_plan(plan, include_contact_persons=True)
        return qs.filter(Q(person__in=persons_available_for_plan) | Q(is_superuser=True))


class PlanScopedLogEntriesView(LogEntriesView):
    results_template_name = "site_history_results.html"
    page_title = pgettext_lazy("page title for history of changes", "Change history")
    LOG_MODELS_TO_EXCLUDE = ModelLogEntry, PageLogEntry
    permission_policy: ModelPermissionPolicy = ModelPermissionPolicy(PlanScopedModelLogEntry)
    filterset_class = CustomSiteHistoryReportFilterSet
    permission_required = 'view'

    # We want to show only PlanScopedModelEntries
    #
    # You might think overriding get_filtered_queryset would be better
    # than overriding get_context_data, but due to the way the view
    # is implemented, that does not work.
    #
    # def get_filtered_queryset(self):
    #     queryset = super().get_filtered_queryset()
    #     indexes_to_ignore = set(self.log_models.index(model) for model in self.LOG_MODELS_TO_EXCLUDE)
    #     return [x for x in queryset if x['log_model_index'] not in indexes_to_ignore]
    #
    def get_context_data(self, *, object_list=None, **kwargs):
        queryset = object_list if object_list is not None else self.object_list
        indexes_to_ignore = set(self.log_models.index(model) for model in self.LOG_MODELS_TO_EXCLUDE)
        queryset = [x for x in queryset if x['log_model_index'] not in indexes_to_ignore]
        return super().get_context_data(object_list=queryset, **kwargs)
