from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from wagtail.admin.admin_url_finder import AdminURLFinder
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin

from kausal_common.users import user_or_bust

from notifications.models import InboxNotification

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse, HttpResponseBase

    from users.models import User

UNREAD_COUNT_CAP = 99
PAGE_SIZE = 20


def inbox_enabled() -> bool:
    return settings.ENABLE_ACTION_MODERATION_UI


def unread_count(user: User) -> int:
    """Return the number of unread notifications, counting at most one past the cap."""
    return InboxNotification.objects.filter(recipient=user).unread()[: UNREAD_COUNT_CAP + 1].count()


def unread_label(count: int) -> str:
    if count > UNREAD_COUNT_CAP:
        return _('More than %(count)d unread notifications') % {'count': UNREAD_COUNT_CAP}
    return ngettext('%(count)d unread notification', '%(count)d unread notifications', count) % {'count': count}


def notification_message(notification: InboxNotification) -> str:
    actor = notification.actor.get_full_name() if notification.actor else _('Someone')
    params = {'actor': actor, 'title': notification.object_title}
    T = InboxNotification.Type
    match notification.type:
        case T.ACTION_SUBMITTED:
            return _('The action "%(title)s" is waiting for your review.') % params
        case T.ACTION_CHANGES_REQUESTED:
            return _('%(actor)s requested changes to the action "%(title)s".') % params
        case T.ACTION_APPROVED:
            return _('%(actor)s approved the action "%(title)s".') % params
        case T.ACTION_WITHDRAWN:
            return _('%(actor)s withdrew the action "%(title)s" from review.') % params
    return notification.object_title


def _require_inbox() -> None:
    if not inbox_enabled():
        raise Http404


def unread_count_view(request: HttpRequest) -> JsonResponse:
    _require_inbox()
    count = unread_count(user_or_bust(request.user))
    return JsonResponse({'count': min(count, UNREAD_COUNT_CAP), 'capped': count > UNREAD_COUNT_CAP, 'label': unread_label(count)})


class InboxView(WagtailAdminTemplateMixin, TemplateView):
    template_name = 'notifications/inbox.html'
    page_title = _('Inbox')
    header_icon = 'fontawesome-bell'

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        _require_inbox()
        return super().dispatch(request, *args, **kwargs)

    def get_page_title(self) -> str:
        return _('Inbox')

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        user = user_or_bust(self.request.user)
        notifications = InboxNotification.objects.filter(recipient=user).unarchived().select_related('actor', 'plan')
        page_obj = Paginator(notifications, PAGE_SIZE).get_page(self.request.GET.get('p'))
        ctx['page_obj'] = page_obj
        ctx['rows'] = [(n, notification_message(n)) for n in page_obj]
        ctx['has_unread'] = notifications.unread().exists()
        return ctx


def open_view(request: HttpRequest, pk: int) -> HttpResponse:
    _require_inbox()
    user = user_or_bust(request.user)
    notification = get_object_or_404(InboxNotification, pk=pk, recipient=user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])
    obj = notification.content_object
    url = AdminURLFinder(user).get_edit_url(obj) if obj is not None else None
    if url is None:
        messages.warning(request, _('"%(title)s" is no longer available.') % {'title': notification.object_title})
        return redirect('notifications_inbox')
    return redirect(url)


@require_POST
def mark_all_read_view(request: HttpRequest) -> HttpResponse:
    _require_inbox()
    user = user_or_bust(request.user)
    InboxNotification.objects.filter(recipient=user).unread().update(read_at=timezone.now())
    return redirect(reverse('notifications_inbox'))
