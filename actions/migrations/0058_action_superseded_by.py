# Generated by Django 3.2.13 on 2022-12-06 13:02

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0057_merge_20221129_1815'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='report',
            options={'verbose_name': 'report', 'verbose_name_plural': 'reports'},
        ),
        migrations.AlterModelOptions(
            name='reporttype',
            options={'verbose_name': 'report type', 'verbose_name_plural': 'report types'},
        ),
        migrations.AddField(
            model_name='action',
            name='superseded_by',
            field=models.ForeignKey(blank=True, help_text='Set if this action is superseded by another action', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='superseded_actions', to='actions.action', verbose_name='superseded by'),
        ),
        migrations.AlterField(
            model_name='attributetype',
            name='report',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attribute_types', to='actions.report', verbose_name='Report'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='settings_action_update_acceptable_interval',
            field=models.PositiveIntegerField(blank=True, help_text='A maximum time interval in days within which actions should always be updated. If you leave this blank the application will use the default value 60.', null=True, validators=[django.core.validators.MaxValueValidator(730), django.core.validators.MinValueValidator(1)], verbose_name='Acceptable interval in days to update actions'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='settings_action_update_target_interval',
            field=models.PositiveIntegerField(blank=True, help_text='A desirable time interval in days within which actions should be updated in the optimal case. If you leave this blank the application will use the default value 30.', null=True, validators=[django.core.validators.MaxValueValidator(365), django.core.validators.MinValueValidator(1)], verbose_name='Target interval in days to update actions'),
        ),
        migrations.AlterField(
            model_name='report',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reports', to='actions.reporttype'),
        ),
    ]
