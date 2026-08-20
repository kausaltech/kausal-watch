from __future__ import annotations

from django.db import migrations
from django.db.models import Count


def backfill_primary_clientplan(apps, schema_editor):
    ClientPlan = apps.get_model('admin_site', 'ClientPlan')
    Plan = apps.get_model('actions', 'Plan')

    plans_with_one_client = Plan.objects.annotate(_n=Count('clients')).filter(_n=1).values_list('id', flat=True)
    ClientPlan.objects.filter(plan_id__in=list(plans_with_one_client), is_primary=False).update(is_primary=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_site', '0018_clientplan_is_primary'),
        ('actions', '0186_public_user_client_scope'),
    ]

    operations = [
        migrations.RunPython(backfill_primary_clientplan, noop_reverse),
    ]
