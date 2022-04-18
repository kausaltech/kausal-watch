import django.db.models.deletion
import modelcluster
import wagtail.core.fields
from django.db import migrations, models

import aplans.utils


def migrate_data(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    action_ct = ContentType.objects.get(app_label='actions', model='action')
    plan_ct = ContentType.objects.get(app_label='actions', model='plan')

    ActionAttributeType = apps.get_model('actions', 'ActionAttributeType')
    AttributeType = apps.get_model('actions', 'AttributeType')
    for instance in ActionAttributeType.objects.all():
        AttributeType.objects.create(
            scope_content_type=plan_ct,
            scope_id=instance.plan.id,
            identifier=instance.identifier,
            name=instance.name,
            format=instance.format,
            order=instance.order,
        )

    ActionAttributeTypeChoiceOption = apps.get_model('actions', 'ActionAttributeTypeChoiceOption')
    AttributeTypeChoiceOption = apps.get_model('actions', 'AttributeTypeChoiceOption')
    for instance in ActionAttributeTypeChoiceOption.objects.all():
        type = AttributeType.objects.get(
            scope_content_type=plan_ct,
            scope_id=instance.type.plan.id,
            identifier=instance.type.identifier,
        )
        AttributeTypeChoiceOption.objects.create(
            type=type,
            identifier=instance.identifier,
            name=instance.name,
            order=instance.order,
        )

    ActionAttributeChoice = apps.get_model('actions', 'ActionAttributeChoice')
    AttributeChoice = apps.get_model('actions', 'AttributeChoice')
    for instance in ActionAttributeChoice.objects.all():
        type = AttributeType.objects.get(
            scope_content_type=plan_ct,
            scope_id=instance.type.plan.id,
            identifier=instance.type.identifier,
        )
        choice = AttributeTypeChoiceOption.objects.get(
            type=type,
            identifier=instance.choice.identifier,
        )
        assert choice.name == instance.choice.name
        AttributeChoice.objects.create(
            type=type,
            content_type=action_ct,
            object_id=instance.action.id,
            choice=choice,
        )

    ActionAttributeChoiceWithText = apps.get_model('actions', 'ActionAttributeChoiceWithText')
    AttributeChoiceWithText = apps.get_model('actions', 'AttributeChoiceWithText')
    for instance in ActionAttributeChoiceWithText.objects.all():
        type = AttributeType.objects.get(
            scope_content_type=plan_ct,
            scope_id=instance.type.plan.id,
            identifier=instance.type.identifier,
        )
        if instance.choice is None:
            choice = None
        else:
            choice = AttributeTypeChoiceOption.objects.get(
                type=type,
                identifier=instance.choice.identifier,
            )
            assert choice.name == instance.choice.name
        AttributeChoiceWithText.objects.create(
            type=type,
            content_type=action_ct,
            object_id=instance.action.id,
            choice=choice,
            text=instance.text,
        )

    ActionAttributeRichText = apps.get_model('actions', 'ActionAttributeRichText')
    AttributeRichText = apps.get_model('actions', 'AttributeRichText')
    for instance in ActionAttributeRichText.objects.all():
        type = AttributeType.objects.get(
            scope_content_type=plan_ct,
            scope_id=instance.type.plan.id,
            identifier=instance.type.identifier,
        )
        AttributeRichText.objects.create(
            type=type,
            content_type=action_ct,
            object_id=instance.action.id,
            text=instance.text,
        )

    ActionAttributeNumericValue = apps.get_model('actions', 'ActionAttributeNumericValue')
    AttributeNumericValue = apps.get_model('actions', 'AttributeNumericValue')
    for instance in ActionAttributeNumericValue.objects.all():
        type = AttributeType.objects.get(
            scope_content_type=plan_ct,
            scope_id=instance.type.plan.id,
            identifier=instance.type.identifier,
        )
        AttributeNumericValue.objects.create(
            type=type,
            content_type=action_ct,
            object_id=instance.action.id,
            value=instance.value,
        )

    # TODO: categories


def migrate_data_reverse(apps, schema_editor):
    pass  # TODO


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('actions', '0023_add_plan_published_archived_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttributeChoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='AttributeChoiceWithText',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('text', wagtail.core.fields.RichTextField(blank=True, null=True, verbose_name='Text')),
            ],
        ),
        migrations.CreateModel(
            name='AttributeNumericValue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('value', models.FloatField()),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
            ],
        ),
        migrations.CreateModel(
            name='AttributeRichText',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('text', wagtail.core.fields.RichTextField(verbose_name='Text')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
            ],
        ),
        migrations.CreateModel(
            name='AttributeType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('scope_id', models.PositiveIntegerField()),
                ('identifier', aplans.utils.IdentifierField(max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier')),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('format', models.CharField(choices=[('ordered_choice', 'Ordered choice'), ('optional_choice', 'Optional choice with optional text'), ('rich_text', 'Rich text'), ('numeric', 'Numeric')], max_length=50, verbose_name='Format')),
                ('scope_content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'attribute type',
                'verbose_name_plural': 'attribute types',
                'unique_together': {('scope_content_type', 'scope_id', 'identifier')},
            },
        ),
        migrations.CreateModel(
            name='AttributeTypeChoiceOption',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('identifier', aplans.utils.IdentifierField(max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier')),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('type', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='choice_options', to='actions.attributetype')),
            ],
            options={
                'verbose_name': 'attribute choice option',
                'verbose_name_plural': 'attribute choice options',
                'ordering': ('type', 'order'),
                'unique_together': {('type', 'order'), ('type', 'identifier')},
            },
        ),
        migrations.AddField(
            model_name='attributerichtext',
            name='type',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='richtext_attributes', to='actions.attributetype'),
        ),
        migrations.AddField(
            model_name='attributenumericvalue',
            name='type',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='numeric_value_attributes', to='actions.attributetype'),
        ),
        migrations.AddField(
            model_name='attributechoicewithtext',
            name='choice',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='choice_with_text_attributes', to='actions.attributetypechoiceoption'),
        ),
        migrations.AddField(
            model_name='attributechoicewithtext',
            name='content_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='attributechoicewithtext',
            name='type',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='choice_with_text_attributes', to='actions.attributetype'),
        ),
        migrations.AddField(
            model_name='attributechoice',
            name='choice',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes', to='actions.attributetypechoiceoption'),
        ),
        migrations.AddField(
            model_name='attributechoice',
            name='content_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype'),
        ),
        migrations.AddField(
            model_name='attributechoice',
            name='type',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes', to='actions.attributetype'),
        ),
        migrations.AlterUniqueTogether(
            name='attributerichtext',
            unique_together={('type', 'content_type', 'object_id')},
        ),
        migrations.AlterUniqueTogether(
            name='attributenumericvalue',
            unique_together={('type', 'content_type', 'object_id')},
        ),
        migrations.AlterUniqueTogether(
            name='attributechoicewithtext',
            unique_together={('type', 'content_type', 'object_id')},
        ),
        migrations.AlterUniqueTogether(
            name='attributechoice',
            unique_together={('type', 'content_type', 'object_id')},
        ),
        migrations.RunPython(migrate_data, migrate_data_reverse),
        migrations.DeleteModel(
            name='ActionAttributeChoice',
        ),
        migrations.DeleteModel(
            name='ActionAttributeChoiceWithText',
        ),
        migrations.DeleteModel(
            name='ActionAttributeNumericValue',
        ),
        migrations.DeleteModel(
            name='ActionAttributeRichText',
        ),
        migrations.DeleteModel(
            name='ActionAttributeType',
        ),
        migrations.DeleteModel(
            name='ActionAttributeTypeChoiceOption',
        ),
        migrations.DeleteModel(
            name='CategoryAttributeChoice',
        ),
        migrations.DeleteModel(
            name='CategoryAttributeNumericValue',
        ),
        migrations.DeleteModel(
            name='CategoryAttributeRichText',
        ),
        migrations.DeleteModel(
            name='CategoryAttributeType',
        ),
        migrations.DeleteModel(
            name='CategoryAttributeTypeChoiceOption',
        ),
    ]
