import logging
from typing import cast

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

from sentry_sdk import capture_exception

from request_log.models import LoggedRequest

logger = logging.getLogger(__name__)


class LogUnsafeRequestMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest):
        if not self._should_process(request):
            return

        try:
            self._log_request(request)
        except Exception as e:
            logger.exception(f'Error logging request: {e}')
            capture_exception(e)

    def _should_process(self, request: HttpRequest) -> bool:
        path = request.get_full_path()
        if request.method not in settings.REQUEST_LOG_METHODS:
            return False
        if path in settings.REQUEST_LOG_IGNORE_PATHS:
            return False
        return True

    def _serialize_file_upload_request(self, request: HttpRequest, content_type: str):
        # For file uploads, we want to store only the form part
        # and keep the text as close to the original HTTP body as possible
        if content_type.startswith('multipart/form-data'):
            # Get the boundary from the content type
            boundary = content_type.split('=')[1]

            # Reconstruct the form data without file contents
            form_data = []
            for key, value in request.POST.items():
                form_data.append(f'--{boundary}\r\n')
                form_data.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n')
                form_data.append(f'{value}\r\n')

            # Add file metadata without actual file content
            for file_key, file_obj in request.FILES.items():
                if not isinstance(file_obj, UploadedFile):
                    continue
                form_data.append(f'--{boundary}\r\n')
                form_data.append(f'Content-Disposition: form-data; name="{file_key}"; filename="{file_obj.name}"\r\n')
                form_data.append(f'Content-Type: {file_obj.content_type}\r\n\r\n')
                form_data.append('[File content not logged]\r\n')

            form_data.append(f'--{boundary}--\r\n')

            # Join all parts to create the final body
            request_body = ''.join(form_data)
        else:
            # If it's not multipart/form-data, log a placeholder
            request_body = '[File upload content not logged]'
        return request_body

    def _log_request(self, request: HttpRequest):
        path = request.get_full_path()
        raw_request = f'{request.method} {path} HTTP/1.1\r\n'
        for header, value in request.META.items():
            if header.startswith('HTTP_'):
                header_name = header[5:].replace('_', '-').title()
                raw_request += f'{header_name}: {value}\r\n'

        content_type = request.META.get('CONTENT_TYPE', '')
        raw_request += f'Content-Type: {request.META["CONTENT_TYPE"]}\r\n'
        content_length = int(request.META.get('CONTENT_LENGTH', 0))
        if request.method == 'POST' and request.FILES:
            request_body = self._serialize_file_upload_request(request, content_type)
        elif content_length < settings.REQUEST_LOG_MAX_BODY_SIZE:
            if not hasattr(request, '_body') and getattr(request, '_read_started', None):
                request_body = '[Content read started]'
            else:
                # For non-file upload requests, proceed as before
                try:
                    request_body = request.body.decode('utf-8')
                except UnicodeDecodeError:
                    request_body = '[UnicodeDecodeError]'
        else:
            request_body = '[Content too large to log]'

        raw_request += f'Content-Length: {content_length}\r\n\r\n'
        raw_request += request_body
        user_id = getattr(request.user, 'id', None)
        impersonator_list = request.session.get("hijack_history", [])
        impersonator = impersonator_list[-1] if impersonator_list else None
        LoggedRequest.objects.create(
            method=cast(str, request.method),
            path=path,
            raw_request=raw_request,
            user_id=user_id,
            impersonator_id=impersonator,
        )
