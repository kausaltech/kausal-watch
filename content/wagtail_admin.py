from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _
from modeltrans.translator import get_i18n_field
from wagtail.admin.panels import FieldPanel, Panel
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets.models import register_snippet

from kausal_common.i18n.panels import TranslatedFieldPanel
from kausal_common.users import user_or_none

from admin_site.menu import PlanSpecificSingletonModelMenuItem
from admin_site.mixins import SuccessUrlEditPageMixin
from admin_site.utils import admin_req
from admin_site.viewsets import WatchEditView, WatchViewSet
from users.models import User

from .models import SiteGeneralContent

if TYPE_CHECKING:
    from actions.models.plan import Plan


# FIXME: This is partly duplicated in actions/wagtail_admin.py.
class SiteGeneralContentPermissionPolicy(ModelPermissionPolicy[SiteGeneralContent, User]):
    def user_has_permission(self, user, action):
        user = user_or_none(user)
        if user is None:
            return False
        if action == 'view':
            return user.is_superuser
        if action == 'add':
            return user.is_superuser
        if action == 'change':
            return user.is_general_admin_for_plan(user.get_active_admin_plan())
        if action == 'delete':
            return False
        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if action == 'change':
            return user.is_general_admin_for_plan(instance.plan)
        return super().user_has_permission_for_instance(user, action, instance)


class SiteGeneralContentMenuItem(PlanSpecificSingletonModelMenuItem):
    def get_one_to_one_field(self, plan: Plan):
        return plan.general_content


class SiteGeneralContentEditView(SuccessUrlEditPageMixin, WatchEditView[SiteGeneralContent]):
    permission_policy: SiteGeneralContentPermissionPolicy

    def user_has_permission(self, permission):
        user = user_or_none(self.request.user)
        if user is None:
            return False
        return self.permission_policy.user_has_permission_for_instance(user, permission, self.object)


class SiteGeneralContentViewSet(WatchViewSet[SiteGeneralContent]):
    model = SiteGeneralContent
    edit_view_class = SiteGeneralContentEditView
    add_to_settings_menu = True
    icon = 'cogs'
    menu_label = _('Site settings')
    menu_order = 502

    @property
    def permission_policy(self):
        return SiteGeneralContentPermissionPolicy(self.model)

    @property
    def panels(self):
        panels = [
            'site_title',
            'site_description',
            'owner_url',
            'owner_name',
            'official_name_description',
            'copyright_text',
            'creative_commons_license',
            'github_api_repository',
            'github_ui_repository',
            'action_term',
            'action_task_term',
            'organization_term',
            'sitewide_announcement',
        ]

        i18n_field = get_i18n_field(self.model)
        assert i18n_field is not None
        i18n_fields = i18n_field.fields
        result: list[Panel[Any]] = []
        for panel in panels:
            if panel in i18n_fields:
                result.append(TranslatedFieldPanel(panel))
            else:
                result.append(FieldPanel(panel))

        return result

    def get_queryset(self, request):
        qs = self.model.objects.get_queryset()
        request = admin_req(request)
        plan = request.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_menu_item(self, order=None):
        return SiteGeneralContentMenuItem(self, order or self.menu_order)


register_snippet(SiteGeneralContentViewSet)
