# Generated by Django 3.1.5 on 2021-08-18 10:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0013_add_migrated_data_to_pages_app_field'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='action_list_lead_content',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='action_short_description',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='dashboard_lead_content',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='hero_content',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='indicator_list_lead_content',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='indicator_short_description',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='migrated_data_to_pages_app',
        ),
    ]
