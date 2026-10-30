from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.forms import BaseFormSet, Form


def submenu_links(response_content: bytes, submenu_label: str | None = None) -> list[tuple[str, str]]:
    """Return the (label, URL) pairs of the links in the admin sidebar's submenu with the given label, or in the whole menu."""
    match = re.search(r'<script id="wagtail-sidebar-props" type="application/json">(.*?)</script>', response_content.decode())
    assert match is not None
    links: list[tuple[str, str]] = []

    def collect(node: Any, inside: bool) -> None:
        if isinstance(node, dict):
            if node.get('_type') == 'wagtail.sidebar.SubMenuItem' and node['_args'][0]['label'] == submenu_label:
                inside = True
            if inside and node.get('_type') == 'wagtail.sidebar.LinkMenuItem':
                links.append((node['_args'][0]['label'], node['_args'][0]['url']))
            for value in node.values():
                collect(value, inside)
        elif isinstance(node, list):
            for value in node:
                collect(value, inside)

    collect(json.loads(match.group(1)), inside=submenu_label is None)
    return links


def post_data(form: Form) -> dict[str, Any]:
    """Flatten a form, formsets included, into the data that submitting it unchanged would post."""
    data: dict[str, Any] = {}

    def add(form: Form) -> None:
        for bound_field in form:
            value = bound_field.value()
            if value is None or value is False:
                continue
            data[bound_field.html_name] = value

    add(form)
    formsets: dict[str, BaseFormSet[Any]] = getattr(form, 'formsets', {})
    for formset in formsets.values():
        add(formset.management_form)
        for child in formset.forms:
            add(child)
    return data
