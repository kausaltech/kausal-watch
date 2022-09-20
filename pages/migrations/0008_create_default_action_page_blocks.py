import typing

from django.db import migrations
from django.db.models import QuerySet
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

if typing.TYPE_CHECKING:
    from django.apps.registry import Apps
    from actions.models import Plan


def forward(apps: 'Apps', schema_editor: BaseDatabaseSchemaEditor):
    from actions.blocks import get_default_action_content_blocks, get_default_action_filter_blocks
    from pages.models import ActionListPage

    pages: QuerySet['ActionListPage'] = ActionListPage.objects.all()
    for page in pages:
        plan: 'Plan' = page.get_site().plan
        blks = get_default_action_content_blocks(plan)
        print('%s <-- %s' % (page, plan))
        for key, val in blks.items():
            assert page._meta.get_field(key)
            setattr(page, key, val)

        blks = get_default_action_filter_blocks(plan)
        for key, val in blks.items():
            assert page._meta.get_field(key)
            setattr(page, key, val)
        page.save()


def reverse():
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0007_customizable_action_pages'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
