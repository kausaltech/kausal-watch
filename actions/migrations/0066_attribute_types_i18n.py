# Generated by Django 3.2.13 on 2023-01-10 14:30

from django.db import migrations, models
import modeltrans.fields

import aplans.utils


def set_primary_language_from_plan(apps, schema_editor):
    AttributeType = apps.get_model('actions', 'AttributeType')
    CategoryType = apps.get_model('actions', 'CategoryType')
    Plan = apps.get_model('actions', 'Plan')
    for at in AttributeType.objects.all():
        scope_app_label = at.scope_content_type.app_label
        scope_model = at.scope_content_type.model
        if scope_app_label == 'actions' and scope_model == 'plan':
            scope = Plan.objects.get(id=at.scope_id)
            plan = scope
        elif scope_app_label == 'actions' and scope_model == 'categorytype':
            scope = CategoryType.objects.get(id=at.scope_id)
            plan = scope.plan
        else:
            raise Exception(f"Unexpected AttributeType scope content type {scope_app_label}:{scope_model}")
        at.primary_language = plan.primary_language
        at.other_languages = plan.other_languages
        at.save()


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0065_plandomain_publication_status_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='attributechoicewithtext',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('text',), required_languages=(), virtual_fields=True),
        ),
        migrations.AddField(
            model_name='attributerichtext',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('text',), required_languages=(), virtual_fields=True),
        ),
        migrations.AddField(
            model_name='attributetext',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('text',), required_languages=(), virtual_fields=True),
        ),
        migrations.AddField(
            model_name='attributetype',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name', 'help_text'), required_languages=(), virtual_fields=True),
        ),
        migrations.AddField(
            model_name='attributetype',
            name='primary_language',
            field=models.CharField(choices=[('da', 'Danish'), ('de', 'German'), ('de-CH', 'German (Switzerland)'), ('en', 'English (United States)'), ('en-GB', 'English (United Kingdom)'), ('en-AU', 'English (Australia)'), ('fi', 'Finnish'), ('sv', 'Swedish')], default='en', max_length=8),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='attributetype',
            name='other_languages',
            field=aplans.utils.ChoiceArrayField(base_field=models.CharField(choices=[('da', 'Danish'), ('de', 'German'), ('de-CH', 'German (Switzerland)'), ('en', 'English (United States)'), ('en-GB', 'English (United Kingdom)'), ('en-AU', 'English (Australia)'), ('fi', 'Finnish'), ('sv', 'Swedish')], max_length=8), blank=True, default=list, null=True, size=None),
        ),
        migrations.AddField(
            model_name='attributetypechoiceoption',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=('name',), required_languages=(), virtual_fields=True),
        ),
        migrations.RunPython(set_primary_language_from_plan, reverse_code=migrations.RunPython.noop),
    ]
