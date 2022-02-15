from wagtail.admin.edit_handlers import (FieldPanel, ObjectList, InlinePanel, RichTextFieldPanel)
from wagtail.contrib.modeladmin.options import modeladmin_register, ModelAdminMenuItem
from django.utils.translation import gettext_lazy as _
from admin_site.wagtail import (
    AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel, CondensedPanelSingleSelect
)

from .models import BaseTemplate


@modeladmin_register
class BaseTemplateAdmin(AplansModelAdmin):
    model = BaseTemplate
    add_to_settings_menu = True

    panels = [
        FieldPanel('from_name'),
        FieldPanel('from_address'),
        FieldPanel('reply_to')
    ]

    templates_panels = [
        FieldPanel('type'),
        FieldPanel('subject')
    ]

    block_panels = [
        RichTextFieldPanel('content'),
        FieldPanel('template', widget=CondensedPanelSingleSelect),
        FieldPanel('identifier', widget=CondensedPanelSingleSelect)
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_menu_item(self, order=None):
        return ActivePlanMenuItem(self, order or self.get_menu_order())

    def get_edit_handler(self, instance, request):
        return AplansTabbedInterface([
            ObjectList(
                self.panels,
                heading=_('Basic information')),
            ObjectList([
                InlinePanel(
                    'templates',
                    panels=self.templates_panels
                )],
                heading=_('Message subjects')),
            ObjectList([
                CondensedInlinePanel(
                    'content_blocks',
                    panels=self.block_panels
                )],
                heading=_('Content')
            )
        ])


class ActivePlanMenuItem(ModelAdminMenuItem):
    # fixme duplicated in actions, content
    def get_context(self, request):
        context = super().get_context(request)
        plan = request.user.get_active_admin_plan()
        if hasattr(plan, 'notification_base_template'):
            context['url'] = self.model_admin.url_helper.get_action_url(
                'edit', plan.notification_base_template.pk)
        return context

    def is_shown(self, request):
        plan = request.user.get_active_admin_plan()
        return hasattr(plan, 'notification_base_template')
