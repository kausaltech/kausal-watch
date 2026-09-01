import modeltrans.fields
import re
from django.db import migrations


def rename_i18n_key(key, old, new):
    return re.sub(rf'^{re.escape(old)}_([a-z]+)$', rf'{new}_\1', key)


MODELS = ['Category', 'CommonCategory', 'CategoryType', 'CommonCategoryType']
OLD_FIELD = 'short_description'
NEW_FIELD = 'lead_paragraph'


def rename_in_i18n_field(apps, schema_editor):
    for model_name in MODELS:
        model = apps.get_model('actions', model_name)
        for instance in model.objects.all():
            if instance.i18n:
                instance.i18n = {
                    rename_i18n_key(k, OLD_FIELD, NEW_FIELD): v
                    for k, v in instance.i18n.items()
                }
                instance.save()


def rename_in_i18n_field_reverse(apps, schema_editor):
    for model_name in MODELS:
        model = apps.get_model('actions', model_name)
        for instance in model.objects.all():
            if instance.i18n:
                instance.i18n = {
                    rename_i18n_key(k, NEW_FIELD, OLD_FIELD): v
                    for k, v in instance.i18n.items()
                }
                instance.save()


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0037_add_category_type_short_description_field'),
    ]

    operations = [
        migrations.RenameField(
            model_name='category',
            old_name='short_description',
            new_name='lead_paragraph',
        ),
        migrations.RenameField(
            model_name='commoncategory',
            old_name='short_description',
            new_name='lead_paragraph',
        ),
        migrations.RenameField(
            model_name='categorytype',
            old_name='short_description',
            new_name='lead_paragraph',
        ),
        migrations.RenameField(
            model_name='commoncategorytype',
            old_name='short_description',
            new_name='lead_paragraph',
        ),
        migrations.AlterField(
            model_name='category',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'lead_paragraph'), required_languages=(), virtual_fields=True),
        ),
        migrations.AlterField(
            model_name='categorytype',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'lead_paragraph'), required_languages=(), virtual_fields=True),
        ),
        migrations.AlterField(
            model_name='commoncategory',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'lead_paragraph'), required_languages=(), virtual_fields=True),
        ),
        migrations.AlterField(
            model_name='commoncategorytype',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'lead_paragraph'), required_languages=(), virtual_fields=True),
        ),
        migrations.RunPython(rename_in_i18n_field, rename_in_i18n_field_reverse)
    ]
