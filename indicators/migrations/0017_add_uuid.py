# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0016_alter_indicator_time_resolution'),
    ]

    operations = [
        migrations.AddField(
            model_name='indicator',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
    ]
