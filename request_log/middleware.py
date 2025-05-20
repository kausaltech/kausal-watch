from __future__ import annotations

from kausal_common.logging.request_log.middleware import LogUnsafeRequestMiddleware as BaseLogUnsafeRequestMiddleware


class LogUnsafeRequestMiddleware(BaseLogUnsafeRequestMiddleware):
    def _add_extra_log_data(self, request, log_data) -> None:
        impersonator_list = request.session.get("hijack_history", [])
        impersonator = impersonator_list[-1] if impersonator_list else None
        log_data['impersonator_id'] = impersonator
