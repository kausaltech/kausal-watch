# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0016_populate_uuid_values'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organization',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
