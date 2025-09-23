from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.urls import resolve
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    schema,
    throttle_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

import requests

from users.models import User


class LoginMethodThrottle(UserRateThrottle):
    rate = '60/m'



def check_user_in_other_clusters(email, request):
    """Check if user exists in other regional clusters."""
    current_host = request.get_host()
    cluster_endpoints = getattr(settings, 'WATCH_BACKEND_REGION_URLS', [])

    # Check that the current host is not a regional endpoint
    if any(current_host == urlparse(endpoint).hostname for endpoint in cluster_endpoints):
        return None

    for endpoint in cluster_endpoints:
        try:
            session = requests.Session()
            csrf_response = session.get(f"{endpoint}/admin/login/")
            csrf_token = session.cookies.get('csrftoken')

            if not csrf_token:
                import re
                csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']', csrf_response.text)
                if csrf_match:
                    csrf_token = csrf_match.group(1)

            response = session.post(
                f"{endpoint}/login/check/",
                json={'email': email},
                timeout=5,
                headers={
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf_token,
                    'Referer': endpoint
                }
            )

            if response.status_code == 200:
                result = response.json()
                result['cluster_url'] = endpoint
                return result

        except requests.exceptions.RequestException as e:
            continue

    return None


@csrf_exempt
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
        cluster_result = check_user_in_other_clusters(email, request)
        if cluster_result:
            msg = _("User found in another cluster. Please go to the following URL to login: <a href='%s/admin/' target='_blank'>%s/admin/</a>") % (
                cluster_result.get('cluster_url'),
                cluster_result.get('cluster_url')
            )
            return Response({
                'method': cluster_result.get('method'),
                'cluster_redirect': True,
                'cluster_url': cluster_result.get('cluster_url')
            })

        msg = _("No user found with this email address. Ask your administrator to create an account for you.")
        raise ValidationError({'detail': msg, 'code': 'no_user'})

    next_url_input = d.get('next')
    resolved = None
    if next_url_input:
        next_url = urlparse(next_url_input)
        resolved = resolve(next_url.path)

    destination_is_public_site = resolved and (
        resolved.url_name == 'authorize' and 'oauth2_provider' in resolved.app_names
    )
    if destination_is_public_site and not user.can_access_public_site(plan=None):
        msg = _(
            "You do not have access to the public site.",
        )
        raise ValidationError({'detail': msg, 'code': 'no_site_access'})

    if not destination_is_public_site and not user.can_access_admin(plan=None):
        msg = _(
            "You do not have admin access. Your administrator may need to assign you an action or indicator, or grant "
            "you plan admin status.",
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
        msg = _("Cannot determine authentication method. The email address domain may be unknown.")
        raise ValidationError({'detail': msg, 'code': 'no_client'})

    if not client.auth_backend:
        msg = _("Password authentication is required, but the user has no password.")
        raise ValidationError({'detail': msg, 'code': 'no_password'})

    return Response({'method': client.auth_backend})
