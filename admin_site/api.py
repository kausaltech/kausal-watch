from django.utils.translation import gettext as _

from rest_framework.decorators import (
    api_view, throttle_classes, schema, authentication_classes, permission_classes
)
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from users.models import User
from users.perms import create_permissions


class LoginMethodThrottle(UserRateThrottle):
    rate = '60/m'


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
@schema(None)
@throttle_classes([LoginMethodThrottle])
def check_login_method(request):
    d = request.data
    if not d or not isinstance(d, dict):
        msg = _("Invalid email address")
        raise ValidationError({'detail': msg, 'code': 'invalid_email'})

    email = d.get('email', '').strip().lower()
    if not email:
        msg = _("Invalid email address")
        raise ValidationError({'detail': msg, 'code': 'invalid_email'})
    user = User.objects.filter(email__iexact=email).first()
    person = user.get_corresponding_person() if user else None
    if user is None or person is None:
        msg = _("No user found with this email address. Ask your administrator to create an account for you.")
        raise ValidationError({'detail': msg, 'code': 'no_user'})

    if not user.can_access_admin():
        msg = _(
            "You do not have admin access. Your administrator may need to assign you an action or indicator, or grant "
            "you plan admin status."
        )
        raise ValidationError({'detail': msg, 'code': 'no_admin_access'})

    # Always use password authentication if the user has a password
    if user.has_usable_password():
        return Response({'method': 'password'})

    # Use the client's authorization backend
    try:
        client = person.get_admin_client()
    except:
        client = None

    if client is None:
        msg = _("Cannot determine authorization method. The email address domain may be unknown.")
        raise ValidationError({'detail': msg, 'code': 'no_client'})

    if not client.auth_backend:
        msg = _("Password authentication is required, but the user has no password.")
        raise ValidationError({'detail': msg, 'code': 'no_password'})

    return Response({'method': client.auth_backend})
