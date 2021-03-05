from django.core.management.base import BaseCommand
from django.db import transaction

from pages.models import CategoryPage, PlanRootPage


def handle_model(model):
    for page in model.objects.all():
        indicator_blocks = (b for b in page.body.stream_data if b['type'] == 'indicator')
        for block in indicator_blocks:
            block['type'] = 'indicator_group'
            block['value'] = [block['value']]
        page.save()


class Command(BaseCommand):
    help = 'Convert IndicatorBlock to IndicatorGroupBlock in streamfields of CategoryPage and PlanRootPage'

    @transaction.atomic
    def handle(self, *args, **options):
        handle_model(CategoryPage)
        handle_model(PlanRootPage)
