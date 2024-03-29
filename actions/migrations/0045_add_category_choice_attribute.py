# Generated by Django 3.2.13 on 2022-10-04 19:30

from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('actions', '0044_alter_planfeatures_public_contact_persons'),
    ]

    operations = [
        migrations.AddField(
            model_name='attributetype',
            name='attribute_category_type',
            field=models.ForeignKey(blank=True, help_text='If the format is "Category", choose which category type the attribute values can be chosen from', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='actions.categorytype', verbose_name='Category type (if format is category)'),
        ),
        migrations.AlterField(
            model_name='attributetype',
            name='format',
            field=models.CharField(choices=[('ordered_choice', 'Ordered choice'), ('optional_choice', 'Optional choice with optional text'), ('rich_text', 'Rich text'), ('numeric', 'Numeric'), ('category_choice', 'Category')], max_length=50, verbose_name='Format'),
        ),
        migrations.CreateModel(
            name='AttributeCategoryChoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('categories', models.ManyToManyField(related_name='_actions_attributecategorychoice_categories_+', to='actions.Category')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contenttypes.contenttype')),
                ('type', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='category_choice_attributes', to='actions.attributetype')),
            ],
            options={
                'unique_together': {('type', 'content_type', 'object_id')},
            },
        ),
    ]
