import logging
from django.conf import settings
from sentry_sdk import capture_exception

from request_log.models import LoggedRequest

logger = logging.getLogger(__name__)


class LogUnsafeRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.get_full_path()
        if request.method in settings.REQUEST_LOG_METHODS and path not in settings.REQUEST_LOG_IGNORE_PATHS:
            try:
                self.log_request(request)
            except Exception as e:
                logger.warning(f'Error logging request: {e}')
                capture_exception(e)
        return self.get_response(request)

    def log_request(self, request):
        path = request.get_full_path()
        raw_request = f'{request.method} {path} HTTP/1.1\r\n'
        for header, value in request.META.items():
            if header.startswith('HTTP_'):
                header_name = header[5:].replace('_', '-').title()
                raw_request += f'{header_name}: {value}\r\n'
        if 'CONTENT_TYPE' in request.META:
            raw_request += f'Content-Type: {request.META["CONTENT_TYPE"]}\r\n'
        try:
            request_body = request.body.decode('utf-8')
        except UnicodeDecodeError:
            request_body = '[UnicodeDecodeError]'
        raw_request += f'Content-Length: {len(request_body)}\r\n\r\n'
        raw_request += request_body
        user_id = getattr(request.user, 'id', None)
        impersonator_list = request.session.get("hijack_history", [])
        impersonator = impersonator_list[-1] if impersonator_list else None
        LoggedRequest.objects.create(
            method=request.method,
            path=path,
            raw_request=raw_request,
            user_id=user_id,
            impersonator_id=impersonator,
        )
