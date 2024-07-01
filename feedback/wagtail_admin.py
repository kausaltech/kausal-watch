from django.contrib.admin.utils import quote
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail.admin.ui.tables import BooleanColumn
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets import widgets as wagtailsnippets_widgets
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import (
    DeleteView, IndexView, InspectView, SnippetViewSet
)

from .models import UserFeedback
from .views import SetUserFeedbackProcessedView


class UserFeedbackPermissionPolicy(ModelPermissionPolicy):
    def user_has_permission(self, user, action):
        if action in ('add', 'change'):
            return False
        if action == 'view':
            return True
        if action == 'delete':
            return user.is_general_admin_for_plan(user.get_active_admin_plan())

        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if action == 'delete':
            return user.is_general_admin_for_plan(instance.plan)
        if action == 'set_is_processed':
            return instance.user_can_change_is_processed(user)

        return super().user_has_permission_for_instance(user, action, instance)


class UserFeedbackDeleteView(DeleteView):
    permission_policy: UserFeedbackPermissionPolicy

    def user_has_permission(self, permission):
        return self.permission_policy.user_has_permission_for_instance(self.request.user, permission, self.object)


class UserFeedbackInspectView(InspectView):
    # FIXME: in yet unreleased Wagtail 6.2.X this is the default, so this line
    # (and the whole class) can be deleted
    any_permission_required = ["add", "change", "delete", "view"]


class UserFeedbackIndexView(IndexView):
    # FIXME: in yet unreleased Wagtail 6.2.X this is the default, so this line
    # can be deleted
    any_permission_required = ["add", "change", "delete", "view"]
    permission_policy: UserFeedbackPermissionPolicy
    set_user_feedback_processed_url_name = None
    set_user_feedback_unprocessed_url_name = None

    def get_edit_url(self, instance: UserFeedback):
        # When the view would normally point to edit view, direct to inspect view instead
        return self.get_inspect_url(instance)

    def get_user_feedback_processed_url(self, instance: UserFeedback):
        return reverse(self.set_user_feedback_processed_url_name, kwargs={'pk': quote(instance.pk)})

    def get_user_feedback_unprocessed_url(self, instance: UserFeedback):
        return reverse(self.set_user_feedback_unprocessed_url_name, kwargs={'pk': quote(instance.pk)})

    def set_processed_button(self, instance: UserFeedback):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_user_feedback_processed_url(instance),
            label=_("Mark as processed"),
            icon_name='check',
            attrs={'aria-label': _("Mark this user feedback as processed")}
        )

    def set_unprocessed_button(self, instance: UserFeedback):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_user_feedback_unprocessed_url(instance),
            label=_("Mark as unprocessed"),
            icon_name='cross',
            attrs={'aria-label': _("Mark this user feedback as unprocessed")}
        )

    def get_list_more_buttons(self, instance: UserFeedback):
        buttons = super().get_list_more_buttons(instance)

        # Hide delete button if user has no delete permission
        if not self.permission_policy.user_has_permission_for_instance(self.request.user, 'delete', instance):
            buttons = [button for button in buttons if button.url != self.get_delete_url(instance)]

        # Do not add the feedback processing button if user lacks permissions
        if not self.permission_policy.user_has_permission_for_instance(self.request.user, 'set_is_processed', instance):
            return buttons

        # Add feedback processing button
        if instance.is_processed:
            process_button = self.set_unprocessed_button(instance)
        else:
            process_button = self.set_processed_button(instance)

        return buttons + [process_button]

class UserFeedbackViewSet(SnippetViewSet):
    model = UserFeedback
    add_to_admin_menu = True
    icon = 'mail'
    menu_label = _('User feedback')
    menu_order = 240
    list_display = ['created_at', 'type', 'action', 'name', 'comment', BooleanColumn('is_processed')]
    list_filter = {'created_at': ['gte'], 'type': ['exact'], 'is_processed': ['exact']}
    inspect_view_enabled = True
    index_view_class = UserFeedbackIndexView
    delete_view_class = UserFeedbackDeleteView
    inspect_view_class = UserFeedbackInspectView
    set_user_feedback_processed_url_name = 'set_user_feedback_processed'
    set_user_feedback_unprocessed_url_name = 'set_user_feedback_unprocessed'

    @property
    def permission_policy(self):
        return UserFeedbackPermissionPolicy(self.model)

    @property
    def set_user_feedback_processed_view(self):
        return self.construct_view(SetUserFeedbackProcessedView, set_processed=True)

    @property
    def set_user_feedback_unprocessed_view(self):
        return self.construct_view(SetUserFeedbackProcessedView, set_processed=False)

    # FIXME: As of writing this latest Wagtail (6.1.X) has a bug which only
    # shows the menu item when user has "add", "change" or "delete" permission,
    # while "view" should be enough. (See
    # https://github.com/wagtail/wagtail/blob/747d70e0656b86e3e8c8d123ecae82fa61cd1438/wagtail/admin/viewsets/model.py#L521C16-L521C58
    # for the specific line of code). This seems to be fixed in the latest
    # still unreleased Wagtail code, so when upgraded to Wagtail 6.2.X this
    # workaround should be safe to delete.
    def get_menu_item(self, order=None):
        menu_item = super().get_menu_item(order)
        menu_item.is_shown = lambda _: True
        return menu_item

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(
            set_user_feedback_processed_url_name=self.get_url_name(self.set_user_feedback_processed_url_name),
            set_user_feedback_unprocessed_url_name=self.get_url_name(self.set_user_feedback_unprocessed_url_name),
            **kwargs
        )

    def get_queryset(self, request):
        qs = self.model.objects.get_queryset()
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_urlpatterns(self):
        urls = super().get_urlpatterns()
        set_user_feedback_processed_url = path(
            f'{self.set_user_feedback_processed_url_name}/<str:pk>/',
            view=self.set_user_feedback_processed_view,
            name=self.set_user_feedback_processed_url_name
        )
        set_user_feedback_unprocessed_url = path(
            f'{self.set_user_feedback_unprocessed_url_name}/<str:pk>/',
            view=self.set_user_feedback_unprocessed_view,
            name=self.set_user_feedback_unprocessed_url_name
        )
        return urls + [
            set_user_feedback_processed_url,
            set_user_feedback_unprocessed_url,
        ]


register_snippet(UserFeedbackViewSet)
