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
`PlanFeatures` row. Making the column nullable lets both releases write: the old one keeps
supplying a value, the new one omits it.

The column is dropped in a later release, once nothing is running that reads it.
"""

from django.db import migrations

COLUMN = 'expose_unpublished_plan_only_to_authenticated_user'

MAKE_NULLABLE = (
    'ALTER TABLE "actions_planfeatures" '
    'ALTER COLUMN "expose_unpublished_plan_only_to_authenticated_user" DROP NOT NULL;'
)

# Going back means the old code reads the column again, so every row needs a value. True was the
# field's default, and it is the safe one: it hid an unpublished plan rather than exposing it.
RESTORE_NOT_NULL = (
    'UPDATE "actions_planfeatures" '
    'SET "expose_unpublished_plan_only_to_authenticated_user" = true '
    'WHERE "expose_unpublished_plan_only_to_authenticated_user" IS NULL;'
    'ALTER TABLE "actions_planfeatures" '
    'ALTER COLUMN "expose_unpublished_plan_only_to_authenticated_user" SET NOT NULL;'
)


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0193_plan_visibility'),
        ('actions', '0194_planfeatures_has_action_task_assignees'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=MAKE_NULLABLE, reverse_sql=RESTORE_NOT_NULL),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='planfeatures',
                    name=COLUMN,
                ),
            ],
        ),
    ]
