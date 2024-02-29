# Generated by Django 3.2.16 on 2024-02-25 14:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0008_person_public_site_only'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='public_site_only',
            field=models.BooleanField(default=False, help_text='Set to enable read-only access to public site without admin access', verbose_name='Allow access to public site only'),
        ),
    ]