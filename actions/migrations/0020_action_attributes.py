# Generated by Django 3.2.12 on 2022-04-05 22:09

import aplans.utils
from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields
import wagtail.fields


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0008_organization_i18n'),
        ('actions', '0019_rename_category_metadata_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActionAttributeType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('identifier', aplans.utils.IdentifierField(
                    max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier'
                )),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('format', models.CharField(
                    choices=[
                        ('ordered_choice', 'Ordered choice'),
                        ('optional_choice', 'Optional choice with optional text'),
                        ('rich_text', 'Rich text'),
                        ('numeric', 'Numeric'),
                    ],
                    max_length=50,
                    verbose_name='Format'
                )),
                ('plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='action_attribute_types',
                    to='actions.plan'
                )),
            ],
            options={
                'verbose_name': 'action attribute type',
                'verbose_name_plural': 'action attribute types',
                'abstract': False,
                'unique_together': {('plan', 'identifier')},
            },
            bases=(models.Model, aplans.utils.PlanRelatedModel),
        ),
        migrations.CreateModel(
            name='ActionAttributeTypeChoiceOption',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('identifier', aplans.utils.IdentifierField(
                    max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier'
                )),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('type', modelcluster.fields.ParentalKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='choice_options',
                    to='actions.actionattributetype'
                )),
            ],
            options={
                'verbose_name': 'action attribute type choice option',
                'verbose_name_plural': 'action attribute type choice options',
                'ordering': ('type', 'order'),
                'abstract': False,
                'unique_together': {('type', 'order'), ('type', 'identifier')},
            },
        ),
        migrations.CreateModel(
            name='ActionAttributeRichText',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', wagtail.fields.RichTextField(verbose_name='Text')),
                ('action', modelcluster.fields.ParentalKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='richtext_attributes', to='actions.action'
                )),
                ('type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='richtext_attributes',
                    to='actions.actionattributetype'
                )),
            ],
            options={
                'unique_together': {('action', 'type')},
            },
        ),
        migrations.CreateModel(
            name='ActionAttributeNumericValue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.FloatField()),
                ('action', modelcluster.fields.ParentalKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='numeric_value_attributes',
                    to='actions.action'
                )),
                ('type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='numeric_value_attributes',
                    to='actions.actionattributetype'
                )),
            ],
            options={
                'unique_together': {('action', 'type')},
            },
        ),
        migrations.CreateModel(
            name='ActionAttributeChoiceWithText',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', wagtail.fields.RichTextField(blank=True, null=True, verbose_name='Text')),
                ('action', modelcluster.fields.ParentalKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='choice_with_text_attributes',
                    to='actions.action'
                )),
                ('choice', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name='choice_with_text_attributes', to='actions.actionattributetypechoiceoption'
                )),
                ('type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='choice_with_text_attributes',
                    to='actions.actionattributetype'
                )),
            ],
            options={
                'unique_together': {('action', 'type')},
            },
        ),
        migrations.CreateModel(
            name='ActionAttributeChoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', modelcluster.fields.ParentalKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes', to='actions.action'
                )),
                ('choice', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes',
                    to='actions.actionattributetypechoiceoption'
                )),
                ('type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes',
                    to='actions.actionattributetype'
                )),
            ],
            options={
                'unique_together': {('action', 'type')},
            },
        ),
    ]
