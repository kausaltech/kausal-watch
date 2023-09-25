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
    # TODO: Don't create permissions here; instead use User.can_access_admin()
    create_permissions(user)
    try:
        client = person.get_admin_client()
    except:
        client = None

    msg = _("This user does not have access to admin.")
    error = ValidationError(dict(detail=msg, code="no_admin_access"))

    if not user.has_perm('wagtailadmin.access_admin'):
        # TODO: distinguish this case to the user, indicating the login was succesful but the plan admins need to assign responsibilities to
        # the person
        raise error
    if user.has_usable_password():
        return Response({'method': 'password'})
    if client is None or not client.auth_backend:
        raise error
    return Response({'method': client.auth_backend})
