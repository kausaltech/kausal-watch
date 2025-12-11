from __future__ import annotations

from wagtail.admin.views.reports.audit_logging import LogEntriesView
from wagtail.models import ModelLogEntry, PageLogEntry


class PlanScopedLogEntriesView(LogEntriesView):
    results_template_name = "site_history_results.html"
    LOG_MODELS_TO_EXCLUDE = ModelLogEntry, PageLogEntry

    # You might think overriding get_filtered_queryset would be better
    # than overriding get_context_data, but due to the way the view
    # is implemented, that does not work.
    #
    # def get_filtered_queryset(self):
    #     queryset = super().get_filtered_queryset()
    #     indexes_to_ignore = set(self.log_models.index(model) for model in self.LOG_MODELS_TO_EXCLUDE)
    #     return [x for x in queryset if x['log_model_index'] not in indexes_to_ignore]

    def get_context_data(self, *, object_list=None, **kwargs):
        queryset = object_list if object_list is not None else self.object_list
        indexes_to_ignore = set(self.log_models.index(model) for model in self.LOG_MODELS_TO_EXCLUDE)
        queryset = [x for x in queryset if x['log_model_index'] not in indexes_to_ignore]
        return super().get_context_data(object_list=queryset, **kwargs)
