# Generated by Django 3.2.13 on 2022-11-24 15:54

import actions.blocks
import aplans.utils
from django.db import migrations, models
import django.db.models.deletion
import wagtail.core.blocks
import wagtail.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0052_add_instances_editable_by_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReportType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('fields', wagtail.core.fields.StreamField([('implementation_phase', actions.blocks.ActionImplementationPhaseReportFieldBlock()), ('text_attribute', wagtail.core.blocks.StructBlock([('name', wagtail.core.blocks.CharBlock(heading='Name')), ('identifier', wagtail.core.blocks.CharBlock(heading='Identifier'))]))], blank=True, null=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='report_types', to='actions.plan')),
            ],
            bases=(models.Model, aplans.utils.PlanRelatedModel),
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('identifier', aplans.utils.IdentifierField(max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier')),
                ('start_date', models.DateField(verbose_name='start date')),
                ('end_date', models.DateField(verbose_name='end date')),
                ('is_complete', models.BooleanField(default=False, help_text='Set if report cannot be changed anymore', verbose_name='complete')),
                ('is_public', models.BooleanField(default=False, help_text='Set if report can be shown to the public', verbose_name='is public')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='actions.reporttype')),
            ],
        ),
        migrations.AddConstraint(
            model_name='report',
            constraint=models.UniqueConstraint(fields=('type', 'identifier'), name='unique_identifier_per_report_type'),
        ),
    ]
