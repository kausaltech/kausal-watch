from __future__ import annotations

from django.apps import AppConfig


def post_reorder_categories(sender, **kwargs):
    from actions.models import CategoryType

    qs = kwargs['queryset']
    type_ids = qs.values_list('type_id')
    for category_type in CategoryType.objects.filter(id__in=type_ids, synchronize_with_pages=True):
        category_type.synchronize_pages()


class PagesConfig(AppConfig):
    name = 'pages'

    def ready(self):
        from pages.wagtail_localize_compat import patch_segment_extraction

        patch_segment_extraction()
