"""
Retire ``expose_unpublished_plan_only_to_authenticated_user`` from the model, but keep the column.

`Plan.visibility` answers this question now, so nothing in this release reads the flag. The
column stays for one release regardless, because migrations run before the previous release's
pods have gone, and those pods consult the flag in `PlanPermissionPolicy` — in the queryset
filters, which every plan read passes through. Dropping the column here would fail their every
request, not some edge case.

Keeping it needs one schema change to go with the state change. The column is ``NOT NULL`` with
no database default (Django drops the default once it has backfilled), so a pod on this release,
which no longer knows the field exists, would violate that constraint the moment it creates a
`PlanFeatures` row. The column therefore gets a database default of true, the field's old
default, which hides an unpublished plan from anonymous visitors. Making the column nullable
instead would not do: the previous release reads NULL as false, which exposes an unpublished
plan — and a row this release creates is exactly that, a new plan nobody has published.

The column is dropped in a later release, once nothing is running that reads it.
"""

from django.db import migrations

COLUMN = 'expose_unpublished_plan_only_to_authenticated_user'

SET_DEFAULT = (
    'ALTER TABLE "actions_planfeatures" ALTER COLUMN "expose_unpublished_plan_only_to_authenticated_user" SET DEFAULT true;'
)

DROP_DEFAULT = (
    'ALTER TABLE "actions_planfeatures" ALTER COLUMN "expose_unpublished_plan_only_to_authenticated_user" DROP DEFAULT;'
)


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0193_plan_visibility'),
        ('actions', '0194_planfeatures_has_action_task_assignees'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=SET_DEFAULT, reverse_sql=DROP_DEFAULT),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='planfeatures',
                    name=COLUMN,
                ),
            ],
        ),
    ]
