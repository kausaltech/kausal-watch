from typing import reveal_type
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, Select
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils import formats

from wagtail.admin.panels import (
    FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel, ObjectList
)
from wagtail.admin.views.account import BaseSettingsPanel, notifications_tab
from wagtail_modeladmin.options import modeladmin_register, ModelAdminMenuItem
from wagtail import hooks

from .forms import NotificationPreferencesForm
from .models import BaseTemplate
from admin_site.wagtail import (
    AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel,
    PlanFilteredFieldPanel, AplansCreateView, AplansEditView, SuccessUrlEditPageMixin,
    AplansAdminModelForm
)
from aplans.context_vars import ctx_request


class BaseTemplateEditView(SuccessUrlEditPageMixin, AplansEditView):
    def get_error_message(self):
        if self.instance.pk:
            return _("Notifications could not be modified due to errors.")
        return _("Notifications could not be set up due to errors.")


class BaseTemplateForm(AplansAdminModelForm):
    def _clean_manually_scheduled_notification_templates(self, formset: BaseFormSet):
        for i, item in enumerate(formset.cleaned_data):
            plan = self.instance.plan
            new_date = item['date']
            local_current_date = plan.now_in_local_timezone().date()
            if item['id'] is None:
                if new_date < local_current_date:
                    formset[i].add_error('date', _('Cannot schedule a notification for the past'))
                continue
            instance = item['id']
            if new_date != instance.date:
                # Rescheduling old notification
                if new_date < local_current_date:
                    formset[i].add_error('date', _('Cannot reschedule a notification for the past'))

    def clean(self):
        formset = self.formsets.get('manually_scheduled_notification_templates', None)
        if formset is not None:
            self._clean_manually_scheduled_notification_templates(formset)
        return super().clean()


@modeladmin_register
class BaseTemplateAdmin(AplansModelAdmin):
    model = BaseTemplate
    add_to_settings_menu = True
    create_view_class = AplansCreateView
    edit_view_class = BaseTemplateEditView
    menu_icon = 'fontawesome-bell'
    menu_label = _('Notifications')

    panels = [
        FieldPanel('from_name'),
        FieldPanel('reply_to'),
    ]

    templates_panels = [
        FieldPanel('type'),
        FieldPanel('subject'),
        FieldPanel('custom_email'),
        MultiFieldPanel([
            FieldRowPanel([
                FieldPanel('send_to_plan_admins'),
                FieldPanel('send_to_custom_email'),
            ]),
            FieldRowPanel([
                FieldPanel('send_to_contact_persons'),
            ]),
        ], heading=_('Recipients'), classname='collapsible'),
    ]

    block_panels = [
        FieldPanel('content'),
        PlanFilteredFieldPanel('template'),
        FieldPanel('identifier')
    ]

    def get_manually_scheduled_notification_panels(self, send_at_time):
        panels = [
            FieldPanel('subject'),
            FieldPanel('date', help_text=(
                format_lazy(
                    '{msg} {time}.',
                    msg=_("The email message will be sent on the specified day at"),
                    time=send_at_time
                )
            )),
            FieldPanel('content'),
            MultiFieldPanel([
                FieldRowPanel([
                    FieldPanel('send_to_plan_admins'),
                    FieldPanel('send_to_action_contact_persons'),
                    FieldPanel('send_to_indicator_contact_persons'),
                    FieldPanel('send_to_organization_admins'),
                    FieldPanel('send_to_custom_email'),
                ]),
                FieldPanel('custom_email'),
            ], classname='collapsible'),
        ]
        return panels

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_menu_item(self, order=None):
        return ActivePlanMenuItem(self, order or self.get_menu_order())

    def get_edit_handler(self):
        request = ctx_request.get()
        additional_panels = []
        if request.user.is_superuser:
            choices = [(email, email) for email in settings.ALLOWED_SENDER_EMAILS]
            additional_panels.append(FieldPanel('from_address', widget=Select(choices=choices)))
            additional_panels.append(FieldPanel('brand_dark_color'))
            additional_panels.append(FieldPanel('logo'))
            additional_panels.append(FieldPanel('font_family'))
            additional_panels.append(FieldPanel('font_css_url'))

        plan = request.user.get_active_admin_plan()
        time = formats.time_format(plan.notification_settings.send_at_time, 'H:i')

        handler = AplansTabbedInterface([
            ObjectList(
                self.panels + additional_panels,
                heading=_('Basic information')),
            ObjectList([
                InlinePanel(
                    'manually_scheduled_notification_templates',
                    panels=self.get_manually_scheduled_notification_panels(time)
                )],
                heading=_('Single notifications')),
            ObjectList([
                InlinePanel(
                    'templates',
                    panels=self.templates_panels
                )],
                heading=_('Automatic notifications')),
            ObjectList([
                CondensedInlinePanel(
                    'content_blocks',
                    panels=self.block_panels
                )],
                heading=_('Notification contents')
            )
        ])
        handler.base_form_class = BaseTemplateForm
        return handler


class ActivePlanMenuItem(ModelAdminMenuItem):
    # fixme duplicated in actions, content
    def render_component(self, request):
        # When clicking the menu item, use the edit view instead of the index view.
        link_menu_item = super().render_component(request)
        plan = request.user.get_active_admin_plan()
        if hasattr(plan, 'notification_base_template'):
            link_menu_item.url = self.model_admin.url_helper.get_action_url('edit', plan.notification_base_template.pk)
        return link_menu_item

    def is_shown(self, request):
        plan = request.user.get_active_admin_plan()
        return hasattr(plan, 'notification_base_template') or request.user.is_superuser


class NotificationsPreferencesPanel(BaseSettingsPanel):
    name = 'notification-preferences'   # Wagtail's admin.views.account already defines 'notifications'
    title = _('Notification preferences')
    tab = notifications_tab
    order = 101
    form_class = NotificationPreferencesForm

    def get_form(self):
        kwargs = {
            'person': self.user.get_corresponding_person(),
        }
        if self.request.method == 'POST':
            return self.form_class(self.request.POST, self.request.FILES, **kwargs)
        else:
            return self.form_class(**kwargs)

    def get_context_data(self):
        return {
            **super().get_context_data(),
            'li_classes': 'label-above',
        }

    def is_active(self):
        # Hide the panel if there are no notification preferences
        return bool(self.get_form().fields)


@hooks.register('register_account_settings_panel')
def register_notifications_panel(request, user, profile):
    return NotificationsPreferencesPanel(request, user, profile)
