from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import SiteGeneralContent
from pages.models import ActionListPage, IndicatorListPage, ImpactGroupPage


class Command(BaseCommand):
    help = "Migrate fields from content.SiteGeneralContent to models in pages app"

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            SiteGeneralContent._meta.get_field('migrated_data_to_pages_app')
        except FieldDoesNotExist as e:
            raise FieldDoesNotExist(f"{e}. Probably you checked out a too recent version of the code.")

        for content in SiteGeneralContent.objects.all():
            assert not content.migrated_data_to_pages_app

            plan_root_page = content.plan.root_page.specific
            for attr in ('hero_content', 'action_short_description', 'indicator_short_description'):
                setattr(plan_root_page, attr, getattr(content, attr))
            plan_root_page.save()

            action_list_page = ActionListPage(
                lead_content=content.action_list_lead_content,
                title='Toimenpiteet',
            )
            plan_root_page.add_child(instance=action_list_page)

            indicator_list_page = IndicatorListPage(
                lead_content=content.indicator_list_lead_content,
                title='Mittarit',
            )
            plan_root_page.add_child(instance=indicator_list_page)

            if content.plan.impact_groups.exists():
                impact_group_page = ImpactGroupPage(
                    lead_content=content.dashboard_lead_content,
                    title='Tilannekuva',
                )
                plan_root_page.add_child(instance=impact_group_page)

            content.migrated_data_to_pages_app = True
            content.save()
