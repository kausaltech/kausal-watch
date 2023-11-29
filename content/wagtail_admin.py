from contextlib import contextmanager
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel
from wagtail_modeladmin.options import ModelAdmin, ModelAdminMenuItem, modeladmin_register
from wagtail_modeladmin.views import EditView

from .models import SiteGeneralContent
from actions.wagtail_admin import ActivePlanPermissionHelper
from admin_site.wagtail import SetInstanceMixin, SuccessUrlEditPageMixin, insert_model_translation_panels
from aplans.context_vars import ctx_instance, ctx_request


# FIXME: This is partly duplicated in actions/wagtail_admin.py.
class SiteGeneralContentPermissionHelper(ActivePlanPermissionHelper):
    def user_can_edit_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj.plan)


# FIXME: This duplicates most of what actions.wagtail_admin.ActivePlanMenuItem is doing.
class SiteGeneralContentMenuItem(ModelAdminMenuItem):
    @contextmanager
    def _hack_url_to_edit_view(self, request):
        # Use the edit view instead of the index view.
        plan = request.user.get_active_admin_plan()
        old_url = self.url
        self.url = self.model_admin.url_helper.get_action_url('edit', plan.general_content.pk)
        yield
        self.url = old_url

    def render_component(self, request):
        with self._hack_url_to_edit_view(request):
            return super().render_component(request)

    def is_active(self, request):
        with self._hack_url_to_edit_view(request):
            return super().is_active(request)

    def is_shown(self, request):
        # The overridden superclass method returns True iff user_can_list from the permission helper returns true. But
        # this menu item is about editing a plan, not listing.
        plan = request.user.get_active_admin_plan()
        return self.model_admin.permission_helper.user_can_edit_obj(request.user, plan.general_content)


class SiteGeneralContentEditView(SuccessUrlEditPageMixin, SetInstanceMixin, EditView):
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
        FieldPanel('action_task_term'),
        FieldPanel('organization_term'),
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
        return super().get_edit_handler()
