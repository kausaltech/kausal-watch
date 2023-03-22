from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0074_change_attribute_type_fields'),
        ('reports', '0003_migrate_legacy_reporting_attributes'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attributetype',
            name='report',
        ),
        migrations.RemoveField(
            model_name='attributetype',
            name='report_field',
        ),
    ]
