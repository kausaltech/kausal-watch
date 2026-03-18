from __future__ import annotations

from wagtail.admin.panels import InlinePanel

from kausal_common.datasets.models import DatasetSchema


class IndicatorMetricsInlinePanel(InlinePanel):
    """
    InlinePanel subclass for managing DatasetMetric instances on an indicator's DatasetSchema.

    DatasetMetric has a ParentalKey to DatasetSchema, not to Indicator.
    This panel overrides `on_model_bound()` to point at DatasetSchema's 'metrics'
    relationship, and relies on IndicatorForm injecting the formset into
    `self.formsets['metrics']`.
    """

    def on_model_bound(self):
        manager = getattr(DatasetSchema, self.relation_name)
        self.db_field = manager.rel
        if not self.label:
            self.label = self.db_field.related_model._meta.verbose_name

    def get_form_options(self):
        # Don't return formset options — the ClusterFormMetaclass can't handle
        # this cross-model relationship. IndicatorForm creates and injects
        # the formset manually.
        return {}


class IndicatorComputationsInlinePanel(InlinePanel):
    """
    InlinePanel subclass for managing DatasetMetricComputation instances on an indicator's DatasetSchema.

    Identical pattern to IndicatorMetricsInlinePanel: overrides on_model_bound()
    to point at DatasetSchema's 'computations' relationship, and relies on
    IndicatorForm injecting the formset into self.formsets['computations'].
    """

    def on_model_bound(self):
        manager = getattr(DatasetSchema, self.relation_name)
        self.db_field = manager.rel
        if not self.label:
            self.label = self.db_field.related_model._meta.verbose_name

    def get_form_options(self):
        return {}
