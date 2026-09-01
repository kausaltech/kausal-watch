from django.db import migrations
from wagtail.blocks.migrations.migrate_operation import MigrateStreamData
from wagtail.blocks.migrations.operations import BaseBlockOperation


class DisableHighlightGoalMet(BaseBlockOperation):
    """
    Set highlight_goal_met to False on existing IndicatorValueColumn blocks.

    The block's default is True so newly created columns show the tick by default;
    this migration preserves the previous (pre-flag) behaviour on existing pages,
    where the tick was unconditionally rendered. Customers that want it on
    (e.g. King County) will re-enable it per column in the admin.
    """

    def apply(self, block_value):
        if not isinstance(block_value, dict):
            return block_value
        block_value['highlight_goal_met'] = False
        return block_value

    @property
    def operation_name_fragment(self):
        return 'disable_highlight_goal_met'


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0070_alter_indicatorlistpage_list_columns'),
    ]

    operations = [
        MigrateStreamData(
            app_name='pages',
            model_name='IndicatorListPage',
            field_name='list_columns',
            operations_and_block_paths=[
                (DisableHighlightGoalMet(), 'value'),
            ],
        ),
    ]
