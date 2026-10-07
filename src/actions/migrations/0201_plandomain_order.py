from django.db import migrations, models


def number_domains_by_pk(apps, schema_editor):
    """Order each plan's domains by pk, which keeps the canonical domain the pk tiebreak picked."""
    PlanDomain = apps.get_model('actions', 'PlanDomain')
    order_in_plan: dict[int, int] = {}
    to_update = []
    for domain in PlanDomain.objects.order_by('plan_id', 'pk'):
        order = order_in_plan.get(domain.plan_id, 0) + 1
        order_in_plan[domain.plan_id] = order
        domain.order = order
        to_update.append(domain)
    PlanDomain.objects.bulk_update(to_update, ['order'])


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0200_action_version'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='plandomain',
            options={'ordering': ('plan', 'order'), 'verbose_name': 'plan domain', 'verbose_name_plural': 'plan domains'},
        ),
        migrations.AddField(
            model_name='plandomain',
            name='order',
            field=models.PositiveIntegerField(default=0, verbose_name='order'),
        ),
        migrations.RunPython(number_domains_by_pk, migrations.RunPython.noop),
    ]
