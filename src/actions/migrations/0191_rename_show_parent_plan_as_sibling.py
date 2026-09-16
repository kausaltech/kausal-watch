"""
Rename the ``show_parent_plan_in_plan_switcher`` field to ``show_parent_plan_as_sibling``.

The rename is in Django's model state only. The column keeps its original name,
so that pods running the previous release -- which select the column by name --
keep working while a deployment rolls out, and while it is rolled back.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0190_backfill_public_user_client'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name='planfeatures',
                    old_name='show_parent_plan_in_plan_switcher',
                    new_name='show_parent_plan_as_sibling',
                ),
                migrations.AlterField(
                    model_name='planfeatures',
                    name='show_parent_plan_as_sibling',
                    field=models.BooleanField(
                        default=False,
                        db_column='show_parent_plan_in_plan_switcher',
                        help_text=(
                            'By default, the public UI treats the parent plan as the plan this one belongs to: '
                            'the plan switcher leaves it out, and the related plans block uses its name as the '
                            'heading instead of listing it. If set, the parent plan is listed alongside the '
                            'sibling plans in both places.'
                        ),
                        verbose_name='Show the parent plan as a sibling plan',
                    ),
                ),
            ],
        ),
    ]
