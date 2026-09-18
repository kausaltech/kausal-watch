"""
Add `Plan.visibility` and derive it from the access rules it replaces.

The mapping preserves today's effective data access exactly, so nothing becomes readable that
was not readable before:

- a plan with `published_at` set, at any time, was already readable anonymously (or will be at
  its scheduled moment), so it becomes `public`;
- a plan with `expose_unpublished_plan_only_to_authenticated_user` false was readable anonymously
  regardless of publication, so it becomes `public` too;
- everything else becomes `internal`, the safe default.

The production-domain exposure this work exists to close is closed by the launch gate on the
hostname, not by narrowing what the API serves.
"""

from django.db import migrations, models


def set_visibility_from_previous_rules(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    Plan.objects.filter(published_at__isnull=False).update(visibility='public')
    Plan.objects.filter(
        published_at__isnull=True,
        features__expose_unpublished_plan_only_to_authenticated_user=False,
    ).update(visibility='public')


def clear_visibility(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    Plan.objects.update(visibility='internal')


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0192_rename_present_plan_hierarchy_as_peers'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='visibility',
            field=models.CharField(
                choices=[('internal', 'Internal'), ('public', 'Public')],
                default='internal',
                help_text=(
                    'Internal: only signed-in users who have been granted access to this plan can view it. '
                    'Public: anyone can view it, without signing in.'
                ),
                max_length=20,
                verbose_name='visibility',
            ),
        ),
        migrations.RunPython(set_visibility_from_previous_rules, clear_visibility),
    ]
