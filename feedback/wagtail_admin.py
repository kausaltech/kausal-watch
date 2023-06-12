from django.contrib.admin.utils import quote
from django.urls import re_path
from django.utils.translation import gettext_lazy as _
from wagtail.contrib.modeladmin.helpers import ButtonHelper, PermissionHelper, AdminURLHelper
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register

from .models import UserFeedback
from .views import SetUserFeedbackProcessedView


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


class UserFeedbackURLHelper(AdminURLHelper):
    def get_action_url(self, action, *args, **kwargs):
        if action == 'edit':
            action = 'inspect'
        return super().get_action_url(action, *args, **kwargs)


class UserFeedbackButtonHelper(ButtonHelper):
    mark_as_processed_button_classnames = []

    def set_processed_button(self, pk, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.mark_as_processed_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('set_user_feedback_processed', quote(pk)),
            'label': _("Mark as processed"),
            'classname': cn,
            'title': _("Mark this user feedback as processed"),
        }

    def set_unprocessed_button(self, pk, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.mark_as_processed_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('set_user_feedback_unprocessed', quote(pk)),
            'label': _("Mark as unprocessed"),
            'classname': cn,
            'title': _("Mark this user feedback as unprocessed"),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)
        if obj.is_processed:
            set_unprocessed_button = self.set_unprocessed_button(obj.pk, **kwargs)
            if set_unprocessed_button:
                buttons.append(set_unprocessed_button)
        else:
            set_processed_button = self.set_processed_button(obj.pk, **kwargs)
            if set_processed_button:
                buttons.append(set_processed_button)
        return buttons


@modeladmin_register
class UserFeedbackAdmin(ModelAdmin):
    model = UserFeedback
    menu_icon = 'mail'
    menu_label = _('User feedbacks')
    menu_order = 240
    permission_helper_class = UserFeedbackPermissionHelper
    list_display = ['created_at', 'type', 'action', 'name', 'comment', 'is_processed']
    list_filter = ['created_at', 'type', 'is_processed']
    inspect_view_enabled = True
    button_helper_class = UserFeedbackButtonHelper
    url_helper_class = UserFeedbackURLHelper

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def set_user_feedback_processed_view(self, request, instance_pk):
        return SetUserFeedbackProcessedView.as_view(
            model_admin=self,
            user_feedback_pk=instance_pk,
            set_processed=True,
        )(request)

    def set_user_feedback_unprocessed_view(self, request, instance_pk):
        return SetUserFeedbackProcessedView.as_view(
            model_admin=self,
            user_feedback_pk=instance_pk,
            set_processed=False,
        )(request)

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        set_user_feedback_processed_url = re_path(
            self.url_helper.get_action_url_pattern('set_user_feedback_processed'),
            self.set_user_feedback_processed_view,
            name=self.url_helper.get_action_url_name('set_user_feedback_processed')
        )
        set_user_feedback_unprocessed_url = re_path(
            self.url_helper.get_action_url_pattern('set_user_feedback_unprocessed'),
            self.set_user_feedback_unprocessed_view,
            name=self.url_helper.get_action_url_name('set_user_feedback_unprocessed')
        )
        return urls + (
            set_user_feedback_processed_url,
            set_user_feedback_unprocessed_url,
        )
