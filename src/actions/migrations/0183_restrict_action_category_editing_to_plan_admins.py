from django.db import migrations


def migrate_data(apps, schema_editor):
    """
    Preserve the effective edit rights of action categories.

    The action form used to show its category fields to plan admins only, ignoring
    `CategoryType.instances_editable_by`. Now that the setting is honoured, category types set to
    "authenticated" would suddenly become editable by every user who may edit an action, so record
    the previous behaviour explicitly.
    """
    CategoryType = apps.get_model('actions', 'CategoryType')
    CategoryType.objects.filter(editable_for_actions=True, instances_editable_by='authenticated').update(
        instances_editable_by='plan_admins'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0182_attributetype_admin_help_text_and_more'),
    ]

    operations = [
        # Not reversible: the category types that were changed cannot be told apart afterwards from
        # the ones that were already restricted to plan admins.
        migrations.RunPython(migrate_data, migrations.RunPython.noop),
    ]
