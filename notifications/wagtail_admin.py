from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.forms import BaseFormSet, Select
from django.urls import reverse
from django.utils import formats
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.panels import (
    FieldPanel,
    FieldRowPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.admin.views.account import BaseSettingsPanel, notifications_tab
from wagtail.snippets.models import register_snippet

from admin_site.mixins import SuccessUrlEditPageMixin
from admin_site.utils import admin_req
from admin_site.viewsets import WatchEditView, WatchViewSet
from admin_site.wagtail import (
    AplansAdminModelForm,
    CondensedInlinePanel,
    PlanFilteredFieldPanel,
)

from .forms import NotificationPreferencesForm
from .models import BaseTemplate

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.db.models import Model
    from django.db.models.query import QuerySet
    from django.http.request import HttpRequest
    from wagtail.admin.forms.models import WagtailAdminModelForm
    from wagtail.admin.panels.base import Panel

class BaseTemplateForm(AplansAdminModelForm):

    def __init__(self, *args, **kwargs):
        if 'plan' in kwargs:
            self.plan = kwargs.pop('plan')
        super().__init__(*args, **kwargs)

    def _clean_manually_scheduled_notification_templates(self, formset: BaseFormSet) -> None:
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


class BaseTemplateEditView(SuccessUrlEditPageMixin, WatchEditView[BaseTemplate, BaseTemplateForm]):
    """Edit view for the BaseTemplate model."""

    def get_error_message(self):
        if self.object.pk:
            return _("Notifications could not be modified due to errors.")
        return _("Notifications could not be set up due to errors.")


class BaseTemplateSendDatePanel(FieldPanel):
    """
    Panel for the send date field of the BaseTemplate model.

    Provides plan-specific help text for the send date field.
    """

    def get_bound_panel(
        self,
        instance: Model | None = None,
        request: HttpRequest | None = None,
        form: WagtailAdminModelForm[Model, AbstractBaseUser] | None = None,
        prefix: str = 'panel'
    ) -> Panel.BoundPanel[
        Panel[Model, WagtailAdminModelForm[Model, AbstractBaseUser]],
        WagtailAdminModelForm[Model, AbstractBaseUser],
        Model,
    ]:
        assert request is not None
        request = admin_req(request)
        plan = request.user.get_active_admin_plan()
        time = formats.time_format(plan.notification_settings.send_at_time, 'H:i')
        self.help_text = format_lazy(
            '{msg} {time}.',
            msg=_("The email message will be sent on the specified day at"),
            time=time,
        )
        return super().get_bound_panel(instance, request, form, prefix)


class BaseTemplateViewSet(WatchViewSet[BaseTemplate, BaseTemplateForm]):
    model = BaseTemplate
    add_to_settings_menu = True
    edit_view_class = BaseTemplateEditView
    icon = 'fontawesome-bell'
    menu_label = _('Notifications')

    panels = [
        FieldPanel('from_name'),
        FieldPanel('reply_to'),
        FieldPanel(
            'from_address',
            widget=Select(choices=[(email, email) for email in settings.ALLOWED_SENDER_EMAILS]),
            permission='superuser',
        ),
        FieldPanel('brand_dark_color', permission='superuser'),
        FieldPanel('logo', permission='superuser'),
        FieldPanel('font_family', permission='superuser'),
        FieldPanel('font_css_url', permission='superuser'),
    ]

    manually_scheduled_notification_panels = [
        FieldPanel('subject'),
        BaseTemplateSendDatePanel('date'),
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
        FieldPanel('identifier'),
    ]

    def get_queryset(self, request: HttpRequest) -> QuerySet[BaseTemplate, BaseTemplate]:
        request = admin_req(request)
        qs = self.model.objects.get_queryset()
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_menu_item(self, order=None):
        return BaseTemplateMenuItem(self, order or self.menu_order)

    def get_edit_handler(self) -> ObjectList | TabbedInterface | None:
        tabs = [
            ObjectList(
                self.panels,
                heading=_('Basic information')),
            ObjectList([
                InlinePanel(
                    'manually_scheduled_notification_templates',
                    panels=self.manually_scheduled_notification_panels,
                )],
                heading=_('One-off notifications')),
            ObjectList([
                InlinePanel(
                    'templates',
                    panels=self.templates_panels,
                )],
                heading=_('Event-based notifications')),
            ObjectList([
                CondensedInlinePanel(
                    'content_blocks',
                    panels=self.block_panels,
                )],
                heading=_('Notification contents'),
            ),
        ]
        handler = TabbedInterface(tabs)
        handler.base_form_class = BaseTemplateForm
        return handler.bind_to_model(self.model)


register_snippet(BaseTemplateViewSet)


# TODO: Similar to PlanSpecificSingletonModelMenuItem, can the use cases be
# merged?  This is a bit different, as the BaseTemplate is not quaranteed to
# exist, it must be created first by a superuser.
class BaseTemplateMenuItem(MenuItem):
    """
    MenuItem for the BaseTemplate model.

    The menu item directs straight to the edit view, if the BaseTemplate is set
    for the active plan. If not, it is only accessible to superusers and it
    directs to the list view, where the BaseTemplate can be created.
    """

    def __init__(self, view_set, order):
        self.view_set = view_set

        super().__init__(
            label=view_set.menu_label,
            url=reverse(self.view_set.get_url_name('list')),
            name=view_set.menu_name,
            icon_name=view_set.icon,
            order=order,
        )

    def render_component(self, request):
        request = admin_req(request)
        link_menu_item = super().render_component(request)
        plan = request.user.get_active_admin_plan()
        if hasattr(plan, 'notification_base_template'):
            link_menu_item.url = reverse(
                self.view_set.get_url_name('edit'),
                kwargs={'pk': plan.notification_base_template.pk},
            )
        return link_menu_item

    def is_shown(self, request):
        request = admin_req(request)
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
