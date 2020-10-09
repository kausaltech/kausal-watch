# Generated by Django 3.1 on 2020-10-08 10:34

from django.db import migrations, models
import modeltrans.fields


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_add_content_block_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentblock',
            name='content_t',
            field=models.TextField(help_text='HTML content for the block', null=True, verbose_name='content'),
        ),
        migrations.AddField(
            model_name='contentblock',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=(), required_languages=(), virtual_fields=True),
        ),
        migrations.AddField(
            model_name='contentblock',
            name='name_t',
            field=models.CharField(max_length=100, null=True, verbose_name='name'),
        ),
        migrations.AddField(
            model_name='notificationtemplate',
            name='html_body_t',
            field=models.TextField(help_text='HTML body for email notifications', null=True, verbose_name='HTML body'),
        ),
        migrations.AddField(
            model_name='notificationtemplate',
            name='subject_t',
            field=models.CharField(help_text='Subject for email notifications', null=True, max_length=200, verbose_name='subject'),
        ),
        migrations.AddField(
            model_name='notificationtemplate',
            name='i18n',
            field=modeltrans.fields.TranslationField(fields=(), required_languages=(), virtual_fields=True),
        ),
    ]
