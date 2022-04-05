from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0018_migrate_plan_features'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CategoryTypeMetadata',
            new_name='CategoryAttributeType',
        ),
        migrations.RenameModel(
            old_name='CategoryTypeMetadataChoice',
            new_name='CategoryAttributeTypeChoiceOption',
        ),
        migrations.RenameModel(
            old_name='CategoryMetadataRichText',
            new_name='CategoryAttributeRichText',
        ),
        migrations.RenameModel(
            old_name='CategoryMetadataChoice',
            new_name='CategoryAttributeChoice',
        ),
        migrations.RenameModel(
            old_name='CategoryMetadataNumericValue',
            new_name='CategoryAttributeNumericValue',
        ),
        migrations.RenameField(
            model_name='categoryattributetypechoiceoption',
            old_name='metadata',
            new_name='type',
        ),
        migrations.AlterField(
            model_name='categoryattributetypechoiceoption',
            name='type',
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='choice_options',
                to='actions.categoryattributetype'
            ),
        ),
        migrations.RenameField(
            model_name='categoryattributetype',
            old_name='type',
            new_name='category_type',
        ),
        migrations.AlterField(
            model_name='categoryattributetype',
            name='category_type',
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='attribute_types', to='actions.categorytype'
            ),
        ),
        migrations.AlterField(
            model_name='categoryattributerichtext',
            name='category',
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='richtext_attributes', to='actions.category'
            ),
        ),
        migrations.RenameField(
            model_name='categoryattributerichtext',
            old_name='metadata',
            new_name='type',
        ),
        migrations.AlterField(
            model_name='categoryattributerichtext',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='richtext_attributes',
                to='actions.categoryattributetype'
            ),
        ),
        migrations.AlterField(
            model_name='categoryattributechoice',
            name='category',
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes', to='actions.category'
            ),
        ),
        migrations.AlterField(
            model_name='categoryattributechoice',
            name='choice',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='categories',
                to='actions.categoryattributetypechoiceoption'
            ),
        ),
        migrations.RenameField(
            model_name='categoryattributechoice',
            old_name='metadata',
            new_name='type',
        ),
        migrations.AlterField(
            model_name='categoryattributetypechoiceoption',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='choice_attributes',
                to='actions.categoryattributetype'
            ),
        ),
        migrations.AlterField(
            model_name='categoryattributenumericvalue',
            name='category',
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='numeric_value_attributes',
                to='actions.category'
            ),
        ),
        migrations.RenameField(
            model_name='categoryattributenumericvalue',
            old_name='metadata',
            new_name='type',
        ),
        migrations.AlterField(
            model_name='categoryattributenumericvalue',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='numeric_value_attributes',
                to='actions.categoryattributetype'
            ),
        ),
        migrations.AlterField(
            model_name='categoryattributenumericvalue',
            name='category',
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='numeric_value_attributes',
                to='actions.category'
            ),
        ),
    ]
