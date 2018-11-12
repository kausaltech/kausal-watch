# Generated by Django 2.1.3 on 2018-11-12 12:56

import actions.models
from django.db import migrations, models
import django.db.models.deletion
import markdownx.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('django_orghierarchy', '0007_auto_20181111_2316'),
    ]

    operations = [
        migrations.CreateModel(
            name='Action',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(db_index=True, editable=False)),
                ('name', models.CharField(max_length=200, verbose_name='name')),
                ('official_name', models.CharField(blank=True, help_text='The name as approved by an official party', max_length=100, null=True, verbose_name='official name')),
                ('identifier', models.CharField(help_text='The identifier for this action (e.g. number)', max_length=50, verbose_name='identifier')),
                ('description', markdownx.models.MarkdownxField(blank=True, help_text='What does this action involve in more detail?', null=True, verbose_name='description')),
                ('impact', models.IntegerField(blank=True, help_text='The impact this action has in measurable quantity (e.g. t CO₂e)', null=True, verbose_name='impact')),
            ],
            options={
                'verbose_name': 'action',
                'verbose_name_plural': 'actions',
                'ordering': ('plan', 'order'),
            },
        ),
        migrations.CreateModel(
            name='ActionResponsibleParty',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(db_index=True, editable=False)),
                ('action', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='actions.Action')),
                ('org', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='django_orghierarchy.Organization')),
            ],
            options={
                'ordering': ['action', 'order'],
            },
        ),
        migrations.CreateModel(
            name='ActionSchedule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(db_index=True, editable=False)),
                ('name', models.CharField(max_length=100)),
                ('begins_at', models.DateField()),
                ('ends_at', models.DateField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'action schedule',
                'verbose_name_plural': 'action schedules',
                'ordering': ('plan', 'order'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(db_index=True, editable=False)),
                ('name', models.CharField(max_length=100)),
                ('identifier', models.CharField(max_length=50)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='actions.Category')),
            ],
            options={
                'verbose_name': 'category',
                'verbose_name_plural': 'categories',
            },
        ),
        migrations.CreateModel(
            name='CategoryType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('identifier', models.CharField(max_length=50)),
            ],
            options={
                'verbose_name': 'category type',
                'verbose_name_plural': 'category types',
                'ordering': ('plan', 'name'),
            },
        ),
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('identifier', models.CharField(max_length=50, unique=True, verbose_name='identifier')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'plan',
                'verbose_name_plural': 'plans',
                'get_latest_by': 'created_at',
            },
        ),
        migrations.AddField(
            model_name='categorytype',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='actions.Plan'),
        ),
        migrations.AddField(
            model_name='category',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='actions.CategoryType'),
        ),
        migrations.AddField(
            model_name='actionschedule',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='actions.Plan'),
        ),
        migrations.AddField(
            model_name='action',
            name='categories',
            field=models.ManyToManyField(blank=True, to='actions.Category', verbose_name='categories'),
        ),
        migrations.AddField(
            model_name='action',
            name='plan',
            field=models.ForeignKey(default=actions.models.latest_plan, on_delete=django.db.models.deletion.CASCADE, to='actions.Plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='action',
            name='responsible_parties',
            field=models.ManyToManyField(blank=True, through='actions.ActionResponsibleParty', to='django_orghierarchy.Organization', verbose_name='responsible parties'),
        ),
        migrations.AddField(
            model_name='action',
            name='schedule',
            field=models.ManyToManyField(blank=True, to='actions.ActionSchedule', verbose_name='schedule'),
        ),
        migrations.AlterUniqueTogether(
            name='categorytype',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='category',
            unique_together={('type', 'identifier')},
        ),
        migrations.AlterIndexTogether(
            name='actionschedule',
            index_together={('plan', 'order')},
        ),
        migrations.AlterIndexTogether(
            name='actionresponsibleparty',
            index_together={('action', 'order')},
        ),
        migrations.AlterIndexTogether(
            name='action',
            index_together={('plan', 'order')},
        ),
    ]
