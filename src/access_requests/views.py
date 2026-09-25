from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from kausal_common.users import user_or_bust

from .emails import send_decision_email
from .models import AccessRequest
from .services import AccessRequestNotPendingError, approve_access_request, reject_access_request

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

    from users.models import User


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
