from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from django.contrib.admin.utils import quote
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail.admin.ui.tables import BooleanColumn
from wagtail.coreutils import multigetattr
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets import widgets as wagtailsnippets_widgets
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import (
    DeleteView,
    IndexView,
    InspectView,
    SnippetViewSet,
)

from kausal_common.users import UserOrAnon, is_authenticated, user_or_bust, user_or_none

from users.models import User

from .models import UserFeedback
from .views import SetUserFeedbackProcessedView

if TYPE_CHECKING:
    from django.db.models.query import QuerySet
    from django.http.request import HttpRequest
    from wagtail.admin.menu import MenuItem


class UserFeedbackPermissionPolicy(ModelPermissionPolicy[UserFeedback, User, str]):
    def user_has_permission(self, user: UserOrAnon, action: str) -> bool:
        if not is_authenticated(user):
            return False
        if action in ('add', 'change'):
            return False
        if action == 'view':
            return True
        if action == 'delete':
            return user.is_general_admin_for_plan(user.get_active_admin_plan())

        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user: User, action: str, instance: UserFeedback) -> bool:
        if action == 'delete':
            return user.is_general_admin_for_plan(instance.plan)
        if action == SetUserFeedbackProcessedView.permission_required:
            return instance.user_can_change_is_processed(user)

        return super().user_has_permission_for_instance(user, action, instance)


class UserFeedbackDeleteView(DeleteView[UserFeedback]):
    permission_policy: UserFeedbackPermissionPolicy  # type: ignore[assignment]

    def user_has_permission(self, permission: str) -> bool:
        user = user_or_none(self.request.user)
        if user is None:
            return False
        return self.permission_policy.user_has_permission_for_instance(user, permission, self.object)


class UserFeedbackInspectView(InspectView):
    # FIXME: in yet unreleased Wagtail 6.2.X this is the default, so this line
    # (and the whole class) can be deleted
    any_permission_required = ['add', 'change', 'delete', 'view']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for field in context['fields']:
            if field['value'] == '' or field['value'] is None:
                field['value'] = 'None'
        return context


class UserFeedbackIndexView(IndexView[UserFeedback]):
    # FIXME: in yet unreleased Wagtail 6.2.X this is the default, so this line
    # can be deleted
    any_permission_required = ['add', 'change', 'delete', 'view']
    permission_policy: UserFeedbackPermissionPolicy  # type: ignore[assignment]
    set_user_feedback_processed_url_name = None
    set_user_feedback_unprocessed_url_name = None
    additional_fields_cache: list[str] | None = None

    @property
    def list_export(self) -> list[str]:
        """List of fields to export to a spreadsheet."""
        return [
            'created_at',
            'type',
            'action',
            'category',
            'url',
            'name',
            'email',
            'is_processed',
            'comment',
        ] + self._get_additional_fields()

    @list_export.setter
    def list_export(self, value) -> None:
        # This setter is needed to be able to define list_export programmatically as property above
        pass

    @property
    def export_filename(self) -> str:
        """Filename given to the exported spreadsheet."""
        return f'{self.get_page_title()} - {user_or_bust(self.request.user).get_active_admin_plan()}'

    @export_filename.setter
    def export_filename(self, value) -> None:
        # This setter is needed to be able to define export_filename programmatically as property above
        pass

    def _get_additional_fields(self) -> list[str]:
        """Get a list of all user-defined additional fields of the feedback form present in the queryset."""
        if self.additional_fields_cache is not None:
            return self.additional_fields_cache

        additional_fields = []
        for feedback in self.get_queryset():
            if feedback.additional_fields is not None:
                additional_fields += feedback.additional_fields.keys()

        duplicates_removed = list(dict.fromkeys(additional_fields))
        self.additional_fields_cache = duplicates_removed
        return self.additional_fields_cache

    def to_row_dict(self, item) -> OrderedDict[str, str]:
        """
        Override the default implementation from SpreadsheetExportMixin.

        Expands 'additional_fields' to individual columns in the exported spreadsheet.
        """
        row_dict = OrderedDict()

        for field in self.list_export:
            try:
                value = multigetattr(item, field)
            except AttributeError:
                # If the field is not an attribute of the feedback model, check if it's one of all additional fields.
                if field not in self._get_additional_fields():
                    raise

                # The field might still not exist in this particular item's additional_fields. Use N/A as a fallback.
                value = _('N/A')
                if item.additional_fields is not None:
                    value = item.additional_fields.get(field, _('N/A'))

            row_dict[field] = value

        return row_dict

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
            label=_('Mark as processed'),
            icon_name='check',
            attrs={'aria-label': _('Mark this user feedback as processed')},
        )

    def set_unprocessed_button(self, instance: UserFeedback):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_user_feedback_unprocessed_url(instance),
            label=_('Mark as unprocessed'),
            icon_name='cross',
            attrs={'aria-label': _('Mark this user feedback as unprocessed')},
        )

    def get_list_more_buttons(self, instance: UserFeedback):
        buttons = super().get_list_more_buttons(instance)

        # Hide delete button if user has no delete permission
        if not self.permission_policy.user_has_permission_for_instance(user_or_bust(self.request.user), 'delete', instance):
            buttons = [button for button in buttons if button.url != self.get_delete_url(instance)]

        # Do not add the feedback processing button if user lacks permissions
        if not self.permission_policy.user_has_permission_for_instance(
            user_or_bust(self.request.user), 'set_is_processed', instance
        ):
            return buttons

        # Add feedback processing button
        if instance.is_processed:
            process_button = self.set_unprocessed_button(instance)
        else:
            process_button = self.set_processed_button(instance)

        return [*buttons, process_button]


class UserFeedbackViewSet(SnippetViewSet[UserFeedback]):
    model = UserFeedback
    add_to_admin_menu = True
    icon = 'mail'
    menu_label = _('User feedback')
    menu_order = 240
    list_display = ['created_at', 'type', 'action', 'category', 'name', 'comment', BooleanColumn('is_processed')]
    list_filter = {'created_at': ['gte'], 'type': ['exact'], 'is_processed': ['exact']}
    inspect_view_enabled = True
    index_view_class = UserFeedbackIndexView
    delete_view_class = UserFeedbackDeleteView
    inspect_view_class = UserFeedbackInspectView
    set_user_feedback_processed_url_name = 'set_user_feedback_processed'
    set_user_feedback_unprocessed_url_name = 'set_user_feedback_unprocessed'

    @property
    def permission_policy(self) -> UserFeedbackPermissionPolicy:
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
    def get_menu_item(self, order: int | None = None) -> MenuItem:
        menu_item = super().get_menu_item(order)
        menu_item.is_shown = lambda _request: True  # type: ignore[assignment]
        return menu_item

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(
            set_user_feedback_processed_url_name=self.get_url_name(self.set_user_feedback_processed_url_name),
            set_user_feedback_unprocessed_url_name=self.get_url_name(self.set_user_feedback_unprocessed_url_name),
            **kwargs,
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[UserFeedback, UserFeedback]:
        qs = self.model.objects.get_queryset()
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_urlpatterns(self):
        urls = super().get_urlpatterns()
        set_user_feedback_processed_url = path(
            f'{self.set_user_feedback_processed_url_name}/<str:pk>/',
            view=self.set_user_feedback_processed_view,
            name=self.set_user_feedback_processed_url_name,
        )
        set_user_feedback_unprocessed_url = path(
            f'{self.set_user_feedback_unprocessed_url_name}/<str:pk>/',
            view=self.set_user_feedback_unprocessed_view,
            name=self.set_user_feedback_unprocessed_url_name,
        )
        return [*urls, set_user_feedback_processed_url, set_user_feedback_unprocessed_url]


register_snippet(UserFeedbackViewSet)
