# Generated by Django 3.2.13 on 2023-02-28 13:16

import autoslug.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0069_attributetype_report_field'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='report',
            name='unique_identifier_per_report_type',
        ),
        migrations.AlterField(
            model_name='attributetype',
            name='identifier',
            field=autoslug.fields.AutoSlugField(always_update=True, editable=False, populate_from='name_for_identifier', unique_with=('object_content_type', 'scope_content_type', 'scope_id')),
        ),
        migrations.AlterField(
            model_name='attributetypechoiceoption',
            name='identifier',
            field=autoslug.fields.AutoSlugField(always_update=True, editable=False, populate_from='name', unique_with=('type',)),
        ),
        migrations.AlterField(
            model_name='report',
            name='identifier',
            field=autoslug.fields.AutoSlugField(always_update=True, editable=False, populate_from='name', unique_with=('type',)),
        ),
        migrations.AlterField(
            model_name='report',
            name='is_public',
            field=models.BooleanField(default=False, help_text='Set if report can be shown to the public', verbose_name='public'),
        ),
    ]