# Generated by Django 3.2.16 on 2023-09-08 13:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0018_add_organization_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organization',
            name='primary_language',
            field=models.CharField(choices=[('da', 'Danish'), ('de', 'German'), ('de-CH', 'German (Switzerland)'), ('en', 'English (United States)'), ('en-AU', 'English (Australia)'), ('en-GB', 'English (United Kingdom)'), ('es', 'Spanish'), ('es-US', 'Spanish (United States)'), ('fi', 'Finnish'), ('lv', 'Latvian'), ('sv', 'Swedish')], max_length=8),
        ),
    ]
