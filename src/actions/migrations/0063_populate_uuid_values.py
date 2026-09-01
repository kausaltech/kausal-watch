# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations
import uuid


def gen_uuid(apps, schema_editor):
    model_names = ['Action', 'Category', 'CommonCategory']
    for model_name in model_names:
        model = apps.get_model('actions', model_name)
        for row in model.objects.all():
            row.uuid = uuid.uuid4()
            row.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0062_add_uuid'),
    ]

    operations = [
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]
