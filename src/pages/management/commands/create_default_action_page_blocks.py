from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand
from django.db import transaction

from pages.models import ActionListPage

if TYPE_CHECKING:
    from django.db.models import QuerySet


class Command(BaseCommand):
    help = 'Create default content blocks in action pages'

    @transaction.atomic
    def handle(self, *args, **options):
        pages: QuerySet[ActionListPage] = ActionListPage.objects.all()
        fields = [
            'primary_filters',
            'main_filters',
            'advanced_filters',
            'details_main_top',
            'details_main_bottom',
            'details_aside',
        ]
        for page in pages:
            if not any(getattr(page, field) for field in fields):
                page.set_default_content_blocks()
