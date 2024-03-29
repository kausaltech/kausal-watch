# Generated by Django 3.2.13 on 2022-09-22 09:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0040_make_help_text_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='planfeatures',
            name='enable_indicator_comparison',
            field=models.BooleanField(default=True, help_text='Set to enable comparing indicators between organizations', null=True, verbose_name='Enable comparing indicators'),
        ),
    ]
