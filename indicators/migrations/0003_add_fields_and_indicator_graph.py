# Generated by Django 2.1.3 on 2018-12-14 22:36

import aplans.utils
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0002_result_high_can_be_null'),
    ]

    operations = [
        migrations.CreateModel(
            name='IndicatorGraph',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', django.contrib.postgres.fields.jsonb.JSONField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'get_latest_by': 'created_at',
            },
        ),
        migrations.AddField(
            model_name='indicator',
            name='identifier',
            field=aplans.utils.IdentifierField(blank=True, max_length=50, null=True, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier'),
        ),
        migrations.AddField(
            model_name='indicator',
            name='level',
            field=models.CharField(blank=True, choices=[('strategic', 'strategic'), ('operational', 'operational')], max_length=30, null=True, verbose_name='level'),
        ),
        migrations.AddField(
            model_name='indicatorestimate',
            name='forecast',
            field=models.BooleanField(default=False, help_text='Is this estimate based on forecast or measurement?', verbose_name='measured'),
        ),
        migrations.AlterField(
            model_name='indicator',
            name='time_resolution',
            field=models.CharField(choices=[('year', 'year'), ('month', 'month'), ('week', 'week'), ('day', 'day')], default='year', max_length=50, verbose_name='time resolution'),
        ),
        migrations.AlterField(
            model_name='indicatorestimate',
            name='rationale',
            field=models.TextField(blank=True, null=True, verbose_name='rationale'),
        ),
        migrations.AddField(
            model_name='indicatorgraph',
            name='indicator',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='graphs', to='indicators.Indicator'),
        ),
        migrations.AddField(
            model_name='indicator',
            name='latest_graph',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='indicators.IndicatorGraph'),
        ),
    ]
