# Generated by Django 3.2.12 on 2022-03-14 14:20

from django.db import migrations
import modeltrans.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0015_actiontask_i18n'),
    ]

    operations = [
        migrations.AlterField(
            model_name='action',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'official_name', 'description', 'manual_status_reason'), required_languages=(), virtual_fields=True),
        ),
    ]
