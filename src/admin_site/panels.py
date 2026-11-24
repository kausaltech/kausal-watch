from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import urlencode
from wagtail.admin.panels import Panel

from kausal_common.users import user_or_bust

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model
    from django_stubs_ext.aliases import StrOrPromise

    from admin_site.models import BaseChangeLogMessage
    from admin_site.viewsets import ObjectWithPublicChangeLogMessage
    from users.models import User


@dataclass
class ChangeLogMessageItem:
    message: BaseChangeLogMessage
    is_public: bool
    is_pending: bool
    edit_url: str | None
    delete_url: str | None


class ChangeLogMessagesPanel(Panel):
    """
    List the change history messages of the object being edited, without any form inputs.

    The object must have a `change_log_messages` relation to a subclass of `BaseChangeLogMessage` that is
    registered as a snippet, and a `get_public_change_log_message()` method. The panel is only shown for
    saved objects in plans that have change history messages enabled.
    """

    def __init__(
        self,
        get_add_url: Callable[[Any, User], str | None],
        *args,
        add_unavailable_text: StrOrPromise | None = None,
        get_message_check: Callable[[Any, User], Callable[[Any], bool]] | None = None,
        **kwargs,
    ):
        """
        Set up the panel.

        `get_add_url(obj, user)` returns the URL for adding a message to the object, or None if the user can't add one
        now, in which case the panel shows `add_unavailable_text`. `get_message_check(obj, user)` returns a check
        whether the user may edit and delete a message, on top of the permission to edit the object.
        """
        self.get_add_url = get_add_url
        self.add_unavailable_text = add_unavailable_text
        self.get_message_check = get_message_check
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        kwargs['get_add_url'] = self.get_add_url
        kwargs['add_unavailable_text'] = self.add_unavailable_text
        kwargs['get_message_check'] = self.get_message_check
        return kwargs

    class BoundPanel(Panel.BoundPanel[Any, Any, Any]):
        panel: ChangeLogMessagesPanel
        template_name = 'aplans/panels/change_log_messages_panel.html'

        def is_shown(self) -> bool:
            if self.instance is None or self.instance.pk is None:
                return False
            plan = user_or_bust(self.request.user).get_active_admin_plan()
            return plan.features.enable_change_log

        def _url_namespace(self, message_model: type[Model]) -> str:
            meta = message_model._meta
            return f'wagtailsnippets_{meta.app_label}_{meta.model_name}'

        @cached_property
        def saved_object(self) -> Any:
            """
            Return the object as saved in the database.

            The edit form of an object with a draft shows the draft, rebuilt from its revision. Wagtail doesn't keep the
            publication state of the saved object when doing so, e.g., the live revision of a snippet.
            """
            return type(self.instance)._default_manager.get(pk=self.instance.pk)

        def get_items(self) -> list[ChangeLogMessageItem]:
            instance = cast('ObjectWithPublicChangeLogMessage', self.saved_object)
            public_message = instance.get_public_change_log_message()
            # Messages tied to a revision newer than the live one belong to changes that are waiting for moderation.
            # Unpublishing removes the live revision. Without one, an object that was never published has only such
            # messages, and an unpublished one only the message of the changes it may have submitted again.
            live_revision_id: int | None = getattr(instance, 'live_revision_id', None)
            never_published = getattr(instance, 'first_published_at', None) is None
            submitted_revision_id: int | None = None
            if live_revision_id is None and not never_published and getattr(instance, 'workflow_in_progress', False):
                submitted_revision_id = getattr(instance, 'latest_revision_id', None)
            user = user_or_bust(self.request.user)
            plan = user.get_active_admin_plan()
            # Indicators can be shared between plans, but each plan only sees its own messages, as in the message views
            messages = (
                self.saved_object.change_log_messages
                .filter(plan=plan)
                .select_related('plan', 'created_by__wagtail_userprofile')
                .order_by('-created_at', '-pk')
            )
            namespace = self._url_namespace(messages.model)
            next_param = urlencode({'next': self.request.get_full_path()})
            may_change_message = (
                self.panel.get_message_check(instance, user) if self.panel.get_message_check else lambda _message: True
            )
            items = []
            # Share one instance per author, so that the avatar's person and image lookups are cached per author
            authors: dict[int, Any] = {}
            for message in messages:
                if message.created_by is not None:
                    message.created_by = authors.setdefault(message.created_by.pk, message.created_by)
                revision_id: int | None = getattr(message, 'revision_id', None)
                if revision_id is None:
                    is_pending = False
                elif live_revision_id is None:
                    is_pending = never_published or revision_id == submitted_revision_id
                else:
                    is_pending = revision_id > live_revision_id
                may_change = may_change_message(message)
                items.append(
                    ChangeLogMessageItem(
                        message=message,
                        is_public=public_message is not None and message.pk == public_message.pk,
                        is_pending=is_pending,
                        edit_url=reverse(f'{namespace}:edit', args=[message.pk]) if may_change else None,
                        delete_url=f'{reverse(f"{namespace}:delete", args=[message.pk])}?{next_param}' if may_change else None,
                    )
                )
            return items

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            context['items'] = self.get_items()
            context['add_url'] = self.panel.get_add_url(self.saved_object, user_or_bust(self.request.user))
            context['add_unavailable_text'] = self.panel.add_unavailable_text
            return context
