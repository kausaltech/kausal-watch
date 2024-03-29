import autoslug.fields
from django.db import migrations, models


def set_show_in_reporting_tab(apps, schema_editor):
    AttributeType = apps.get_model('actions', 'AttributeType')
    for attribute_type in AttributeType.objects.all():
        if attribute_type.report:
            attribute_type.show_in_reporting_tab = True
            attribute_type.save()


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0073_rename_report_tables'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attributetype',
            name='identifier',
            field=autoslug.fields.AutoSlugField(always_update=True, editable=False, populate_from='name', unique_with=('object_content_type', 'scope_content_type', 'scope_id')),
        ),
        migrations.AddField(
            model_name='attributetype',
            name='show_in_reporting_tab',
            field=models.BooleanField(default=False, verbose_name='show in reporting tab'),
        ),
        migrations.RunPython(set_show_in_reporting_tab, reverse_code=migrations.RunPython.noop),
    ]
