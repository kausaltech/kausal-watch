# Generated by Django 3.2.12 on 2022-04-07 05:47

import aplans.utils
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0020_action_attributes'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='theme_identifier',
            field=aplans.utils.IdentifierField(blank=True, max_length=50, null=True, validators=[aplans.utils.IdentifierValidator()], verbose_name='Theme identifier'),
        ),
    ]
