# Generated by Django 3.1.5 on 2021-03-01 11:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0012_delete_old_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitegeneralcontent',
            name='migrated_data_to_pages_app',
            field=models.BooleanField(default=False),
        ),
    ]
