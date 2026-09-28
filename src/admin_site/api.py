from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
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

from .login_method import LoginMethodError, resolve_login_method


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
            response = requests.post(
                f'{endpoint}/login/check/', json={'email': email}, timeout=5, headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                result = response.json()
                result['cluster_url'] = endpoint
                return result

        except requests.exceptions.RequestException:
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
        msg = _('Invalid email address')
        raise ValidationError({'detail': msg, 'code': 'invalid_email'})

    email = d.get('email', '')
    try:
        result = resolve_login_method(email, d.get('next'))
    except LoginMethodError as e:
        if e.code == 'no_user':
            cluster_result = check_user_in_other_clusters(email.strip().lower(), request)
            if cluster_result:
                return Response({
                    'method': cluster_result.get('method'),
                    'cluster_redirect': True,
                    'cluster_url': cluster_result.get('cluster_url'),
                })
        raise ValidationError({'detail': e.detail, 'code': e.code}) from e

    return Response({'method': result.method})
