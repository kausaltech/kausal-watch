# Generated by Django 3.2.13 on 2022-08-08 17:55

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0032_minor_changes'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='action_days_until_considered_stale',
            field=models.PositiveIntegerField(blank=True, help_text='Actions not updated since this many days are considered stale. If you leave this blank the default of 180 will be used', null=True, validators=[django.core.validators.MaxValueValidator(730)], verbose_name='Days until actions considered stale'),
        ),
    ]
