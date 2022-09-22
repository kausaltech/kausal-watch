from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import QuerySet

from pages.models import ActionListPage


class Command(BaseCommand):
    help = "Create default content blocks in action pages"

    @transaction.atomic
    def handle(self, *args, **options):
        pages: QuerySet['ActionListPage'] = ActionListPage.objects.all()
        fields = ['primary_filters', 'main_filters', 'advanced_filters', 'details_main_top', 'details_main_bottom',
                  'details_aside']
        for page in pages:
            if not any(getattr(page, field) for field in fields):
                page.set_default_content_blocks()
