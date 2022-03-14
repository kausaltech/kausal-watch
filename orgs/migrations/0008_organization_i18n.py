# Generated by Django 3.2.12 on 2022-03-14 15:50

from django.db import migrations
import modeltrans.fields


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0007_rename_organizationadmin_organizationplanadmin'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'abbreviation'), required_languages=(), virtual_fields=True),
        ),
    ]
