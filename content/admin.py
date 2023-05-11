from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from wagtail.contrib.modeladmin.views import EditView

from .models import SiteGeneralContent
from aplans.context_vars import ctx_instance, ctx_request
from actions.wagtail_admin import ActivePlanPermissionHelper, PlanSpecificSingletonModelMenuItem
from admin_site.wagtail import SetInstanceMixin, SuccessUrlEditPageMixin, insert_model_translation_panels


# FIXME: This is partly duplicated in actions/wagtail_admin.py.
class SiteGeneralContentPermissionHelper(ActivePlanPermissionHelper):
    def user_can_edit_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj.plan)


class SiteGeneralContentMenuItem(PlanSpecificSingletonModelMenuItem):
    def get_one_to_one_field(self, plan):
        return plan.general_content


class SiteGeneralContentEditView(SetInstanceMixin, SuccessUrlEditPageMixin, EditView):
    pass


@modeladmin_register
class SiteGeneralContentAdmin(ModelAdmin):
    model = SiteGeneralContent
    edit_view_class = SiteGeneralContentEditView
    permission_helper_class = SiteGeneralContentPermissionHelper
    add_to_settings_menu = True
    menu_icon = 'cogs'
    menu_label = _('Site settings')
    menu_order = 503

    panels = [
        FieldPanel('site_title'),
        FieldPanel('site_description'),
        FieldPanel('owner_url'),
        FieldPanel('owner_name'),
        FieldPanel('official_name_description'),
        FieldPanel('copyright_text'),
        FieldPanel('creative_commons_license'),
        FieldPanel('github_api_repository'),
        FieldPanel('github_ui_repository'),
        FieldPanel('action_term'),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_menu_item(self, order=None):
        return SiteGeneralContentMenuItem(self, order or self.get_menu_order())

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()
        self.panels = insert_model_translation_panels(
            SiteGeneralContent, self.panels, request, instance.plan
        )
        return super().get_edit_handler(instance, request)
