# Generated by Django 3.2.16 on 2024-02-28 14:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0005_make_snapshot_version_unique'),
    ]

    operations = [
        migrations.AlterField(
            model_name='report',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='reports.reporttype'),
        ),
    ]