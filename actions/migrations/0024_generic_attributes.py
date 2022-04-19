import django.db.models.deletion
import modelcluster
import wagtail.core.fields
from django.db import migrations, models

import aplans.utils


def migrate_for_attribute_type(
    apps, attribute_ct, attribute_type_scope_ct, attribute_type_model, attribute_type_choice_option_model,
    attribute_choice_model, attribute_choice_with_text_model, attribute_rich_text_model, attribute_numeric_value_model,
    get_attribute_type_scope, get_attribute_choice_object, get_attribute_choice_with_text_object,
    get_attribute_rich_text_object, get_attribute_numeric_value_object
):
    AttributeType = apps.get_model('actions', 'AttributeType')
    for instance in attribute_type_model.objects.all():
        AttributeType.objects.create(
            object_content_type=attribute_ct,
            scope_content_type=attribute_type_scope_ct,
            scope_id=get_attribute_type_scope(instance).id,
            identifier=instance.identifier,
            name=instance.name,
            format=instance.format,
            order=instance.order,
        )

    AttributeTypeChoiceOption = apps.get_model('actions', 'AttributeTypeChoiceOption')
    for instance in attribute_type_choice_option_model.objects.all():
        type = AttributeType.objects.get(
            object_content_type=attribute_ct,
            scope_content_type=attribute_type_scope_ct,
            scope_id=get_attribute_type_scope(instance.type).id,
            identifier=instance.type.identifier,
        )
        AttributeTypeChoiceOption.objects.create(
            type=type,
            identifier=instance.identifier,
            name=instance.name,
            order=instance.order,
        )

    AttributeChoice = apps.get_model('actions', 'AttributeChoice')
    for instance in attribute_choice_model.objects.all():
        type = AttributeType.objects.get(
            object_content_type=attribute_ct,
            scope_content_type=attribute_type_scope_ct,
            scope_id=get_attribute_type_scope(instance.type).id,
            identifier=instance.type.identifier,
        )
        choice = AttributeTypeChoiceOption.objects.get(
            type=type,
            identifier=instance.choice.identifier,
        )
        assert choice.name == instance.choice.name
        AttributeChoice.objects.create(
            type=type,
            content_type=attribute_ct,
            object_id=get_attribute_choice_object(instance).id,
            choice=choice,
        )

    if attribute_choice_with_text_model is not None:
        assert get_attribute_choice_with_text_object is not None
        AttributeChoiceWithText = apps.get_model('actions', 'AttributeChoiceWithText')
        for instance in attribute_choice_with_text_model.objects.all():
            type = AttributeType.objects.get(
                object_content_type=attribute_ct,
                scope_content_type=attribute_type_scope_ct,
                scope_id=get_attribute_type_scope(instance.type).id,
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
                content_type=attribute_ct,
                object_id=get_attribute_choice_with_text_object(instance).id,
                choice=choice,
                text=instance.text,
            )

    AttributeRichText = apps.get_model('actions', 'AttributeRichText')
    for instance in attribute_rich_text_model.objects.all():
        type = AttributeType.objects.get(
            object_content_type=attribute_ct,
            scope_content_type=attribute_type_scope_ct,
            scope_id=get_attribute_type_scope(instance.type).id,
            identifier=instance.type.identifier,
        )
        AttributeRichText.objects.create(
            type=type,
            content_type=attribute_ct,
            object_id=get_attribute_rich_text_object(instance).id,
            text=instance.text,
        )

    AttributeNumericValue = apps.get_model('actions', 'AttributeNumericValue')
    for instance in attribute_numeric_value_model.objects.all():
        type = AttributeType.objects.get(
            object_content_type=attribute_ct,
            scope_content_type=attribute_type_scope_ct,
            scope_id=get_attribute_type_scope(instance.type).id,
            identifier=instance.type.identifier,
        )
        AttributeNumericValue.objects.create(
            type=type,
            content_type=attribute_ct,
            object_id=get_attribute_numeric_value_object(instance).id,
            value=instance.value,
        )


def migrate_data(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    # Actions
    migrate_for_attribute_type(
        apps,
        attribute_ct=ContentType.objects.get(app_label='actions', model='action'),
        attribute_type_scope_ct=ContentType.objects.get(app_label='actions', model='plan'),
        attribute_type_model=apps.get_model('actions', 'ActionAttributeType'),
        attribute_type_choice_option_model=apps.get_model('actions', 'ActionAttributeTypeChoiceOption'),
        attribute_choice_model=apps.get_model('actions', 'ActionAttributeChoice'),
        attribute_choice_with_text_model=apps.get_model('actions', 'ActionAttributeChoiceWithText'),
        attribute_rich_text_model=apps.get_model('actions', 'ActionAttributeRichText'),
        attribute_numeric_value_model=apps.get_model('actions', 'ActionAttributeNumericValue'),
        get_attribute_type_scope=lambda attribute_type: attribute_type.plan,
        get_attribute_choice_object=lambda attribute_choice: attribute_choice.action,
        get_attribute_choice_with_text_object=lambda acwt: acwt.action,
        get_attribute_rich_text_object=lambda art: art.action,
        get_attribute_numeric_value_object=lambda anv: anv.action,
    )
    # Categories
    migrate_for_attribute_type(
        apps,
        attribute_ct=ContentType.objects.get(app_label='actions', model='category'),
        attribute_type_scope_ct=ContentType.objects.get(app_label='actions', model='categorytype'),
        attribute_type_model=apps.get_model('actions', 'CategoryAttributeType'),
        attribute_type_choice_option_model=apps.get_model('actions', 'CategoryAttributeTypeChoiceOption'),
        attribute_choice_model=apps.get_model('actions', 'CategoryAttributeChoice'),
        attribute_choice_with_text_model=None,  # CategoryAttributeChoiceWithText does not exist
        attribute_rich_text_model=apps.get_model('actions', 'CategoryAttributeRichText'),
        attribute_numeric_value_model=apps.get_model('actions', 'CategoryAttributeNumericValue'),
        get_attribute_type_scope=lambda attribute_type: attribute_type.category_type,
        get_attribute_choice_object=lambda attribute_choice: attribute_choice.category,
        get_attribute_choice_with_text_object=None,  # CategoryAttributeChoiceWithText does not exist
        get_attribute_rich_text_object=lambda art: art.category,
        get_attribute_numeric_value_object=lambda anv: anv.category,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('actions', '0023_add_plan_published_archived_fields'),
    ]

    operations = [
        # Forgot that sometime in the past and now we'd get an error without it
        migrations.AlterModelOptions(
            name='categoryattributetypechoiceoption',
            options={
                'ordering': ('type', 'order'),
            },
        ),
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
                ('object_content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
            ],
            options={
                'verbose_name': 'attribute type',
                'verbose_name_plural': 'attribute types',
                'unique_together': {('object_content_type', 'scope_content_type', 'scope_id', 'identifier')},
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
        migrations.RunPython(migrate_data),
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
