"""
Add `Plan.visibility` and derive it from the access rules it replaces.

The mapping preserves today's effective data access, so nothing becomes readable that was not
readable before:

- a plan published in the past was already readable anonymously, so it becomes `public`;
- a plan with `expose_unpublished_plan_only_to_authenticated_user` false was readable anonymously
  regardless of publication, so it becomes `public` too;
- a plan with a domain whose `publication_status_override` forced it published was served to
  anyone at that hostname, whatever the plan's own state, so it becomes `public` as well;
- everything else becomes `internal`, the safe default.

Scheduled plans — a publication date still in the future — are the awkward case when the flag hid
them, because the old rule gated on `published_at <= now` and the new model has no equivalent
auto-flip for *data*. Marking them `public` would expose their data immediately, before the date
they were scheduled for. Marking them `internal` alone would be worse in a different way: the
domain still launches on schedule, so at that moment the site would appear as a sign-in wall
rather than as the plan.

So their schedule is cleared along with it, leaving them plainly unpublished and internal. That
cancels a schedule somebody set, which is why the affected plans are named in the migration
output: each one needs publishing deliberately, and this is the only moment that knows which
they were.

A scheduled plan with the flag off needs none of this: its data was already readable, so it
becomes `public` and keeps its date, and its domain launches on schedule as before.

Note that clearing the date is not reversible: the backwards migration restores the visibility
default but cannot restore a publication date it did not record.
"""

from django.db import migrations, models
from django.utils import timezone


def decide_visibility(published_at, exposed_only_to_authenticated, has_published_override, now):
    """
    Apply the old access rules to one plan.

    Returns the visibility it should have, and whether its publication date should be cleared.
    Kept free of any model access so the rules can be read, and tested, on their own.
    """
    if has_published_override:
        # The overridden hostname served the plan to anyone before any other rule was consulted.
        # A schedule stays as it is: the plan was readable already, and its other domains launch
        # on the date as before.
        return 'public', False
    if published_at is not None and published_at <= now:
        # Already published, so it was readable by anyone.
        return 'public', False
    if published_at is not None and not exposed_only_to_authenticated:
        # Scheduled, but already readable by anyone; the launch date carries over as it is.
        return 'public', False
    if published_at is not None:
        # Scheduled and hidden. Neither answer preserves the old behaviour, so the schedule goes
        # too; see this migration's docstring.
        return 'internal', True
    # Never published: the flag decided, and it hid the plan when set.
    return ('internal' if exposed_only_to_authenticated else 'public'), False


def set_visibility_from_previous_rules(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    PlanDomain = apps.get_model('actions', 'PlanDomain')
    now = timezone.now()
    unscheduled = []
    overridden = set(PlanDomain.objects.filter(publication_status_override='published').values_list('plan_id', flat=True))

    for plan in Plan.objects.select_related('features').iterator():
        visibility, clear_schedule = decide_visibility(
            plan.published_at,
            plan.features.expose_unpublished_plan_only_to_authenticated_user,
            plan.pk in overridden,
            now,
        )
        fields = ['visibility']
        plan.visibility = visibility
        if clear_schedule:
            unscheduled.append((plan.identifier, plan.published_at))
            plan.published_at = None
            fields.append('published_at')
        plan.save(update_fields=fields)

    if unscheduled:
        print(
            f'\n{len(unscheduled)} plan(s) were scheduled for publication and have been left '
            'internal and unscheduled. Publish each one deliberately when it is due:'
        )
        for identifier, published_at in sorted(unscheduled):
            print(f'  {identifier} (was scheduled for {published_at.isoformat()})')


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
