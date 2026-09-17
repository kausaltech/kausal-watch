"""
Rename the ``show_parent_plan_as_sibling`` field to ``present_plan_hierarchy_as_peers``.

The flag governs how a plan presents its parent/child links in both directions -- a
plan with a parent, and a plan with children -- but its name spoke only of the first.
As with the previous rename, this is Django model state only: the column keeps the
name it was born with, so pods running the previous release keep working.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0191_rename_show_parent_plan_as_sibling'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name='planfeatures',
                    old_name='show_parent_plan_as_sibling',
                    new_name='present_plan_hierarchy_as_peers',
                ),
                migrations.AlterField(
                    model_name='planfeatures',
                    name='present_plan_hierarchy_as_peers',
                    field=models.BooleanField(
                        default=False,
                        db_column='show_parent_plan_in_plan_switcher',
                        help_text=(
                            'If this is a parent plan, consider it one more peer among related plans and show it '
                            'in selectors. If this is a child plan, consider its parent as one more peer among '
                            'related plans and show it in selectors. Should be enabled both in parent and child '
                            'plans when the parent is not considered an umbrella plan.'
                        ),
                        verbose_name='Present the parent-child plans as peers',
                    ),
                ),
            ],
        ),
    ]
