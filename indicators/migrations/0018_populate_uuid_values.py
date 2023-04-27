# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations
import uuid


def gen_uuid(apps, schema_editor):
    Indicator = apps.get_model('indicators', 'Indicator')
    for row in Indicator.objects.all():
        row.uuid = uuid.uuid4()
        row.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0017_add_uuid'),
    ]

    operations = [
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]
