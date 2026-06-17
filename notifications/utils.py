from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

RESERVED_TLDS = ('.localhost', '.local', '.internal', '.test', '.invalid')


def is_valid_public_domain_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname == 'localhost' or hostname.endswith('.localhost'):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return False
    if any(hostname.endswith(tld) for tld in RESERVED_TLDS):
        return False
    return True


def _check_value(value: object, path: str, results: list[tuple[str, str]]) -> None:
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        results.append((path, value))
    elif isinstance(value, (dict, list)):
        results.extend(find_urls_in_context(value, path))


def find_urls_in_context(context: dict | list, _prefix: str = '') -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    if isinstance(context, dict):
        for key, value in context.items():
            _check_value(value, f'{_prefix}.{key}' if _prefix else key, results)
    elif isinstance(context, list):
        for i, item in enumerate(context):
            _check_value(item, f'{_prefix}[{i}]', results)
    return results


def validate_notification_context_urls(context: dict, *, allow_localhost: bool = False) -> None:
    if allow_localhost:
        return
    urls = find_urls_in_context(context)
    invalid = [(path, url) for path, url in urls if not is_valid_public_domain_url(url)]
    if invalid:
        details = ', '.join(f'{path}: {url}' for path, url in invalid)
        raise ValueError(f'Notification context contains non-public URLs: {details}')
