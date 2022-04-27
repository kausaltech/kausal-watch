from django.core.management.base import BaseCommand
from django.db import transaction
from logging import getLogger

from orgs.models import Organization

logger = getLogger(__name__)


class Command(BaseCommand):
    help = "Reset the primary language of organizations to the one of the first related plan (trying ancestors too)"

    @transaction.atomic
    def handle(self, *args, **options):
        for org in Organization.objects.all():
            ancestor = org
            related_plan = None
            while not related_plan and ancestor:
                related_plan = ancestor.plans.first() or ancestor.related_plans.first()
                ancestor = ancestor.get_parent()
            if related_plan:
                org.primary_language = related_plan.primary_language
                org.save()
            else:
                logger.warning(f"Could not determine primary language of organization {org}")
