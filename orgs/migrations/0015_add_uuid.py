# https://docs.djangoproject.com/en/4.1/howto/writing-migrations/#migrations-that-add-unique-fields

from django.db import migrations, models
import uuid

import aplans.utils


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0014_auto_20220812_0914'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name='organization',
            name='primary_language',
            field=models.CharField(choices=[('da', 'Danish'), ('de', 'German'), ('de-CH', 'German (Switzerland)'), ('en', 'English (United States)'), ('en-GB', 'English (United Kingdom)'), ('en-AU', 'English (Australia)'), ('fi', 'Finnish'), ('sv', 'Swedish')], default=aplans.utils.get_default_language, max_length=8),
        ),
    ]
