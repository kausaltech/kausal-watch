from django.utils.translation import gettext_lazy as _
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from .models import UserFeedback


class UserFeedbackPermissionHelper(PermissionHelper):
    def user_can_list(self, user):
        return True

    def user_can_create(self, user):
        return False

    def user_can_inspect_obj(self, user, obj):
        return True

    def user_can_delete_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj)

    def user_can_edit_obj(self, user, obj):
        return False


@modeladmin_register
class UserFeedbackAdmin(ModelAdmin):
    model = UserFeedback
    menu_icon = 'mail'
    menu_label = _('User feedbacks')
    permission_helper_class = UserFeedbackPermissionHelper
    list_display = ['created_at', 'name', 'comment']
    inspect_view_enabled = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)
