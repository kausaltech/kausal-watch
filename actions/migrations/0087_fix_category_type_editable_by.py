from django.db import migrations, models


def migrate_data(apps, schema_editor):
    CategoryType = apps.get_model('actions', 'CategoryType')
    CategoryType.objects.filter(instances_editable_by='').update(instances_editable_by='authenticated')


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0086_contact_persons_public_data'),
    ]

    operations = [
        migrations.RunPython(migrate_data),
    ]
