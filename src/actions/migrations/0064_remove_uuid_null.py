# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0063_populate_uuid_values'),
    ]

    operations = [
        migrations.AlterField(
            model_name='action',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='category',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='commoncategory',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
