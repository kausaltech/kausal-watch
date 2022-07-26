from wagtail.admin.edit_handlers import (FieldPanel, ObjectList, InlinePanel, RichTextFieldPanel)
from wagtail.contrib.modeladmin.options import modeladmin_register, ModelAdminMenuItem
from django.utils.translation import gettext_lazy as _
from admin_site.wagtail import (
    AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel, CondensedPanelSingleSelect,
    PlanFilteredFieldPanel, AplansCreateView, AplansEditView, SuccessUrlEditPageMixin
)

from .models import BaseTemplate


class BaseTemplateEditView(SuccessUrlEditPageMixin, AplansEditView):
    pass


@modeladmin_register
class BaseTemplateAdmin(AplansModelAdmin):
    model = BaseTemplate
    add_to_settings_menu = True
    create_view_class = AplansCreateView
    edit_view_class = BaseTemplateEditView
    menu_icon = 'fa-bell'
    menu_label = _('Notifications')

    panels = [
        FieldPanel('from_name'),
        FieldPanel('reply_to')
    ]

    templates_panels = [
        FieldPanel('type'),
        FieldPanel('subject')
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

    def get_edit_handler(self, instance, request):
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
        return hasattr(plan, 'notification_base_template') or request.user.is_superuser
