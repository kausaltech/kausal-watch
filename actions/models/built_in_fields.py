from itertools import chain
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin, PlanRelatedModel


def get_built_in_field_name_choices():
    # Ideally we should get the fields dynamically. Perhaps it's easier to get from ActionAdmin rather than the
    # Action model because the latter has many fields that are not relevant for BuiltInActionAttributeType due to not
    # being editable or being just technical details (e.g., i18n).
    from actions.action_admin import ActionAdmin
    from actions.models.action import Action
    panels = chain(
        ActionAdmin.basic_panels,
        ActionAdmin.basic_related_panels,
        ActionAdmin.basic_related_panels_general_admin,
        ActionAdmin.progress_panels,
        ActionAdmin.reporting_panels,
    )
    field_names = [panel.field_name for panel in panels if isinstance(panel, FieldPanel)]
    # TODO: BuiltInFieldCustomization also supports other models than Action, but for now restrict ourselves to actions
    return [(field_name, Action._meta.get_field(field_name).verbose_name) for field_name in field_names]


class BuiltInFieldCustomization(InstancesEditableByMixin, InstancesVisibleForMixin, models.Model, PlanRelatedModel):
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='built_in_action_attribute_types')
    # Model of the customized field
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    # Name of the field in the model
    field_name = models.CharField(max_length=80, choices=get_built_in_field_name_choices(), verbose_name=_('field'))

    help_text_override = models.TextField(verbose_name=_('help text'), blank=True)
    label_override = models.TextField(verbose_name=_('label'), blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['plan', 'content_type', 'field_name'], name='unique_field_per_plan')
        ]

    def clean_field_name(self):
        # Note that this will only be called when saving the instance using a form, not when doing it with save(). Since
        # for now we don't have an model admin class for this model but rely on creating instances manually in the REPL,
        # we must manually trigger the validation by calling full_clean().
        model = self.content_type.model_class()
        try:
            model._meta.get_field(self.field_name)
        except FieldDoesNotExist:
            raise ValidationError(_("%(field)s is not a valid field in the model '%(model)s'") % {
                'field': self.field_name,
                'model': self.content_type.model
            })
        return self.field_name
