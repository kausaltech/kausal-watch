"""
Retire ``password_protected`` from the model, but keep the column.

The flag never protected anything; its only effect was to leave the plan out of other plans'
search results. `Plan.visibility` is what keeps a test site behind a sign-in, and
`Plan.exclude_from_search` keeps a plan out of search.

The column stays for one release, because migrations run before the previous release's pods
have gone, and those pods select it on every `PlanFeatures` read. It is ``NOT NULL`` with no
database default, so it gets one of false, the field's old default; otherwise a pod on this
release would violate the constraint whenever it creates a `PlanFeatures` row.

The column is dropped in a later release, once nothing is running that reads it.
"""

from django.db import migrations

COLUMN = 'password_protected'

SET_DEFAULT = 'ALTER TABLE "actions_planfeatures" ALTER COLUMN "password_protected" SET DEFAULT false;'

DROP_DEFAULT = 'ALTER TABLE "actions_planfeatures" ALTER COLUMN "password_protected" DROP DEFAULT;'


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0196_rename_show_login_link_in_public_ui'),
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
