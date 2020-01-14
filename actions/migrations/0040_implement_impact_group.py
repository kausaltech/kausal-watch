# Generated by Django 2.2.9 on 2020-01-14 15:44

import aplans.utils
from django.db import migrations, models
import django.db.models.deletion
import parler.fields
import parler.models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0039_increase_category_short_description_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImpactGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', aplans.utils.IdentifierField(max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier')),
                ('weight', models.FloatField(blank=True, null=True, verbose_name='weight')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='actions.ImpactGroup', verbose_name='parent')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='impact_groups', to='actions.Plan', verbose_name='plan')),
            ],
            options={
                'verbose_name': 'scenario',
                'verbose_name_plural': 'scenarios',
                'ordering': ('plan', '-weight'),
                'unique_together': {('plan', 'identifier')},
            },
            bases=(parler.models.TranslatableModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ImpactGroupTranslation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('language_code', models.CharField(db_index=True, max_length=15, verbose_name='Language')),
                ('name', models.CharField(max_length=200, verbose_name='name')),
                ('master', parler.fields.TranslationsForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='translations', to='actions.ImpactGroup')),
            ],
            options={
                'verbose_name': 'scenario Translation',
                'db_table': 'actions_impactgroup_translation',
                'db_tablespace': '',
                'managed': True,
                'default_permissions': (),
                'unique_together': {('language_code', 'master')},
            },
            bases=(parler.models.TranslatedFieldsModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ImpactGroupAction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='impact_groups', to='actions.Action', verbose_name='action')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='actions.ImpactGroup', verbose_name='name')),
                ('impact', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='actions.ActionImpact', verbose_name='impact')),
            ],
            options={
                'verbose_name': 'impact group action',
                'verbose_name_plural': 'impact group actions',
                'unique_together': {('group', 'action')},
            },
        ),
    ]
