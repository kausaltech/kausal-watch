# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations
import uuid


def gen_uuid(apps, schema_editor):
    model_names = ['Person']
    for model_name in model_names:
        model = apps.get_model('people', model_name)
        for row in model.objects.all():
            row.uuid = uuid.uuid4()
            row.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0005_add_uuid'),
    ]

    operations = [
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]
