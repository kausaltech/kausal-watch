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
    rate = '5/m'


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
@schema(None)
@throttle_classes([LoginMethodThrottle])
def check_login_method(request):
    d = request.data
    if not d or not isinstance(d, dict):
        msg = _("Invalid email address")
        raise ValidationError(dict(detail=msg, code="invalid_email"))

    email = d.get('email', '').strip().lower()
    if not email:
        msg = _("Invalid email address")
        raise ValidationError(dict(detail=msg, code="invalid_email"))
    user = User.objects.filter(email__iexact=email).first()
    person = user.get_corresponding_person() if user else None
    if user is None or person is None:
        msg = _("No user found with this email address. Ask your administrator to create an account for you.")
        raise ValidationError(dict(detail=msg, code="no_user"))

    # Before we check for permissions, we may need to create them first
    create_permissions(user)
    # Missing client also means no admin access
    try:
        client = person.get_admin_client()
    except:
        client = None
    if not user.has_perms(['wagtailadmin.access_admin']) or client is None:
        msg = _("This user does not have access to admin.")
        raise ValidationError(dict(detail=msg, code="no_admin_access"))

    if user.has_usable_password() or not client.auth_backend:
        method = 'password'
    else:
        method = client.auth_backend
    return Response({"method": method})
