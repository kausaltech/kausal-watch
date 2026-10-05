from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from kausal_common.users import user_or_bust

from notifications.models import DEFAULT_BRAND_DARK_COLOR, DEFAULT_FONT_FAMILY

from .emails import get_plan_url, may_set_password, send_decision_email
from .models import AccessRequest
from .services import AccessRequestNotPendingError, approve_access_request, reject_access_request

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse, HttpResponseBase

    from users.models import User

# The public UI page an approved visitor lands on once they have set their password.
ACCESS_APPROVED_PATH = '/access-approved'


def _decide(
    request: HttpRequest,
    pk: int,
    decide: Callable[[AccessRequest, User], AccessRequest],
    success_message: str,
    unsent_message: str,
) -> HttpResponse:
    user = user_or_bust(request.user)
    plan = user.get_active_admin_plan()
    req = get_object_or_404(AccessRequest, pk=pk)
    if req.plan_id != plan.pk or not user.is_general_admin_for_plan(plan) or not plan.features.enable_access_requests:
        raise PermissionDenied
    try:
        req = decide(req, user)
    except AccessRequestNotPendingError:
        messages.warning(request, _('The access request from %(email)s was already handled.') % {'email': req.email})
        return redirect('wagtailadmin_home')
    # The decision is committed by now, so the email tells the visitor something that holds.
    if send_decision_email(req):
        messages.success(request, success_message % {'email': req.email})
    else:
        messages.warning(request, unsent_message % {'email': req.email})
    return redirect('wagtailadmin_home')


# Not atomic as a whole: the decision must be committed before the email about it goes out, and
# the admin must hear in this response if the email could not be sent.
@transaction.non_atomic_requests
@require_POST
def approve_view(request: HttpRequest, pk: int) -> HttpResponse:
    return _decide(
        request,
        pk,
        lambda req, user: approve_access_request(req, by=user),
        success_message=_('Access approved for %(email)s. They have been notified by email.'),
        unsent_message=_('Access approved for %(email)s, but the email to them could not be sent.'),
    )


@transaction.non_atomic_requests
@require_POST
def reject_view(request: HttpRequest, pk: int) -> HttpResponse:
    return _decide(
        request,
        pk,
        lambda req, user: reject_access_request(req, by=user),
        success_message=_('Access request from %(email)s rejected. They have been notified by email.'),
        unsent_message=_('Access request from %(email)s rejected, but the email to them could not be sent.'),
    )


class SetPasswordView(auth_views.PasswordResetConfirmView):
    """
    Let an approved visitor set their password from the link in the approval email.

    Signs them in, so the public site's sign-in goes through without asking for the password again.
    """

    template_name = 'access_requests/set_password.html'
    post_reset_login = True
    # Several backends are configured, so the login must name the one that checks passwords.
    post_reset_login_backend = 'django.contrib.auth.backends.ModelBackend'
    access_request: AccessRequest

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponseBase:
        self.access_request = get_object_or_404(AccessRequest.objects.select_related('plan', 'person__user'), pk=kwargs['pk'])
        with translation.override(self.access_request.plan.primary_language):
            response = super().dispatch(request, *args, **kwargs)
            # A template response renders only after the view returns, outside the override.
            if isinstance(response, TemplateResponse):
                response.render()
        return response

    def get_user(self, uidb64: str) -> User | None:
        user = super().get_user(uidb64)
        # Anyone the request does not vouch for gets the same "invalid link" page as a bad token.
        if not may_set_password(self.access_request, user):
            return None
        return user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plan = self.access_request.plan
        context['plan_name'] = plan.name_i18n
        context['plan_url'] = get_plan_url(plan) or ''
        general_content = getattr(plan, 'general_content', None)
        context['site_title'] = (general_content.site_title if general_content else '') or plan.name_i18n
        # The public UI's theme is not available here, so borrow the branding of the plan's emails.
        base_template = getattr(plan, 'notification_base_template', None)
        if base_template is not None:
            context['theme'] = base_template.get_notification_context()['theme']
        else:
            context['theme'] = {
                'brand_dark_color': DEFAULT_BRAND_DARK_COLOR,
                'font_family_with_fallback': DEFAULT_FONT_FAMILY,
                'font_css_url': None,
            }
        return context

    def get_success_url(self) -> str:
        return self.access_request.plan.get_view_url().rstrip('/') + ACCESS_APPROVED_PATH
