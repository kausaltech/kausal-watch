from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from wagtail.admin.edit_handlers import (
    FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel, ObjectList, RichTextFieldPanel
)
from wagtail.admin.views.account import BaseSettingsPanel, notifications_tab
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.core import hooks

from .forms import NotificationPreferencesForm
from .models import BaseTemplate
from admin_site.wagtail import (
    AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel, CondensedPanelSingleSelect,
    PlanFilteredFieldPanel, AplansCreateView, AplansEditView, SafeLabelModelAdminMenuItem, SuccessUrlEditPageMixin
)
from aplans.context_vars import ctx_request


class BaseTemplateEditView(SuccessUrlEditPageMixin, AplansEditView):
    pass


@modeladmin_register
class BaseTemplateAdmin(AplansModelAdmin):
    model = BaseTemplate
    add_to_settings_menu = True
    create_view_class = AplansCreateView
    edit_view_class = BaseTemplateEditView
    menu_icon = 'fa-bell'
    menu_label = pgettext_lazy('hyphenated', 'Notifications')

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
        RichTextFieldPanel('content'),
        PlanFilteredFieldPanel('template', widget=CondensedPanelSingleSelect),
        FieldPanel('identifier', widget=CondensedPanelSingleSelect)
    ]

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
            additional_panels.append(FieldPanel('from_address'))
            additional_panels.append(FieldPanel('brand_dark_color'))
            additional_panels.append(FieldPanel('logo'))
            additional_panels.append(FieldPanel('font_family'))
            additional_panels.append(FieldPanel('font_css_url'))

        return AplansTabbedInterface([
            ObjectList(
                self.panels + additional_panels,
                heading=_('Basic information')),
            ObjectList([
                InlinePanel(
                    'templates',
                    panels=self.templates_panels
                )],
                heading=_('Notification types')),
            ObjectList([
                CondensedInlinePanel(
                    'content_blocks',
                    panels=self.block_panels
                )],
                heading=_('Notification contents')
            )
        ])


class ActivePlanMenuItem(SafeLabelModelAdminMenuItem):
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
