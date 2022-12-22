from django import forms
from django.utils.translation import gettext_lazy as _
from wagtail.admin.widgets import SwitchInput

from .models import GeneralPlanAdminNotificationPreferences, ActionContactPersonNotificationPreferences


class NotificationPreferencesForm(forms.Form):
    # Map model to an identifier used in form field names
    MODEL_ID = {
        ActionContactPersonNotificationPreferences: 'acp',
        GeneralPlanAdminNotificationPreferences: 'gcp',
    }
    MODEL_FOR_ID = {id: model for model, id in MODEL_ID.items()}

    # Map model to list of tuples (model field name, form field label, help text)
    MODEL_FIELDS = {
        ActionContactPersonNotificationPreferences: [
            ('receive_general_action_notifications',
             lambda obj: _("General notifications for action '%s'") % obj.action_contact_person.action,
             _("These are sent when there are news about this action such as reminders for deadlines.")),
            ('receive_action_feedback_notifications',
             lambda obj: _("Feedback notifications for action '%s'") % obj.action_contact_person.action,
             _("These are sent when a visitor has left feedback for this action.")),
        ],
        GeneralPlanAdminNotificationPreferences: [
            ('receive_feedback_notifications',
             lambda obj: _("Feeback notifications for plan '%s'") % obj.general_plan_admin.plan,
             _("These are sent when a visitor has left feedback for this plan.")),
        ],
    }

    def __init__(self, *args, **kwargs):
        self.person = kwargs.pop('person')
        super().__init__(*args, **kwargs)
        for model, model_id in self.MODEL_ID.items():
            qs = self.get_qs_for_model(model)
            for instance in qs:
                for model_field, label, help_text in self.MODEL_FIELDS[model]:
                    initial = getattr(instance, model_field)
                    field_name = f'{model_id}:{instance.pk}:{model_field}'
                    self.fields[field_name] = forms.BooleanField(
                        required=False,
                        initial=initial,
                        label=label(instance),
                        help_text=help_text,
                        widget=SwitchInput(),
                    )

    def get_qs_for_model(self, model):
        if self.person is None:
            return model.objects.none()

        if model is ActionContactPersonNotificationPreferences:
            return model.objects.filter(
                pk__in=self.person.actioncontactperson_set.values_list('notification_preferences')
            )
        elif model is GeneralPlanAdminNotificationPreferences:
            return model.objects.filter(
                pk__in=self.person.general_admin_plans_ordered.values_list('notification_preferences')
            )
        raise ValueError(f"Unexpected model {model}")

    def cleaned_data_by_model(self):
        """Rearrange self.cleaned_data to access it by model and PK"""
        data_by_model = {}
        for field_name, value in self.cleaned_data.items():
            model_id, pk_str, model_field = field_name.split(':')
            model = self.MODEL_FOR_ID[model_id]
            pk = int(pk_str)
            data_by_model.setdefault(model, {})
            instance_data = data_by_model[model].setdefault(pk, {})
            assert model_field not in instance_data
            instance_data[model_field] = value
        return data_by_model

    def save(self):
        data_by_model = self.cleaned_data_by_model()
        for model, data in data_by_model.items():
            pks = data.keys()
            instances = list(self.get_qs_for_model(model).filter(pk__in=pks))
            for instance in instances:
                instance_data = data_by_model[model][instance.pk]
                for field_name, value in instance_data.items():
                    setattr(instance, field_name, value)
            fields = [field_name for field_name, _, _ in self.MODEL_FIELDS[model]]
            model.objects.bulk_update(instances, fields)
