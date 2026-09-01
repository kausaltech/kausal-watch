from __future__ import annotations

from django.apps import AppConfig

from wagtailorderable.signals import post_reorder


def post_reorder_categories(sender, **kwargs):
    from actions.models import CategoryType

    qs = kwargs['queryset']
    type_ids = qs.values_list('type_id')
    for category_type in CategoryType.objects.filter(id__in=type_ids, synchronize_with_pages=True):
        category_type.synchronize_pages()


class PagesConfig(AppConfig):
    name = 'pages'

    def ready(self):
        from actions.category_admin import CategoryAdmin

        post_reorder.connect(
            post_reorder_categories,
            sender=CategoryAdmin,
            dispatch_uid='reorder_category_pages',
        )
