from __future__ import annotations

import strawberry as sb
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from graphql import GraphQLError

from aplans import gql

from actions.public_user_auth import EMAIL_MAX_LENGTH, enforce_rate_limit

from .models import AccessRequest
from .services import create_access_request, normalize_email

RATE_LIMIT_GROUP = 'access_request'
RATE_LIMIT = '5/m'
# Beyond this many waiting requests a plan takes no more, so a script cannot bury the admins' list.
MAX_PENDING_PER_PLAN = 500
NAME_MAX_LENGTH = AccessRequest._meta.get_field('first_name').max_length or 0


@sb.input
class RequestPlanAccessInput:
    email: str
    first_name: str = ''
    last_name: str = ''


@sb.type
class RequestPlanAccessResult:
    ok: bool = sb.field(description='Always true; the result does not say whether a request was recorded.')


def _clean_email(email: str) -> str:
    email = normalize_email(email)
    try:
        if len(email) > EMAIL_MAX_LENGTH:
            raise ValidationError('too long')  # noqa: TRY301
        validate_email(email)
    except ValidationError:
        raise GraphQLError('Enter a valid email address.', extensions={'code': 'INVALID_EMAIL'}) from None
    return email


@sb.type
class AccessRequestMutations:
    # A plain mutation rather than `gql.mutation`: every refusal is a coded GraphQLError, so there is
    # no OperationInfo to return, and the public UI gets a plain result type.
    @sb.mutation(description="Ask for access to the request's plan, which plan admins then approve or reject.")
    def request_plan_access(self, info: gql.Info, input: RequestPlanAccessInput) -> RequestPlanAccessResult:
        plan = info.context.request_plan
        if plan is None:
            raise GraphQLError('No plan in the request context.', extensions={'code': 'PLAN_REQUIRED'})
        if not plan.features.enable_access_requests:
            raise GraphQLError('This plan does not take access requests.', extensions={'code': 'ACCESS_REQUESTS_DISABLED'})
        enforce_rate_limit(info, RATE_LIMIT_GROUP, RATE_LIMIT)
        email = _clean_email(input.email)
        first_name, last_name = input.first_name.strip(), input.last_name.strip()
        if max(len(first_name), len(last_name)) > NAME_MAX_LENGTH:
            raise GraphQLError('Name is too long.', extensions={'code': 'INVALID_NAME'})
        if AccessRequest.objects.qs.pending().filter(plan=plan).count() >= MAX_PENDING_PER_PLAN:
            raise GraphQLError('Too many requests are waiting for review.', extensions={'code': 'TOO_MANY_PENDING'})
        with transaction.atomic():
            create_access_request(plan, email, first_name=first_name, last_name=last_name)
        return RequestPlanAccessResult(ok=True)
