# Generated by Django 3.1.5 on 2021-01-22 15:54

from django.db import migrations, models
import django.db.models.deletion
import modeltrans.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0065_add_unique_together_constraint_to_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='color',
            field=models.CharField(blank=True, help_text='Set if the category has a theme color', max_length=50, null=True, verbose_name='theme color'),
        ),
        migrations.AlterField(
            model_name='action',
            name='manual_status_reason',
            field=models.TextField(blank=True, help_text='Describe the reason why this action has has this status', null=True, verbose_name='reason for status'),
        ),
        migrations.CreateModel(
            name='CategoryLevel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('name', models.CharField(max_length=100, verbose_name='name')),
                ('i18n', modeltrans.fields.TranslationField(fields=('name',), required_languages=(), virtual_fields=True)),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='levels', to='actions.categorytype', verbose_name='type')),
            ],
            options={
                'verbose_name': 'category level',
                'verbose_name_plural': 'category levels',
                'ordering': ('type', 'order'),
                'unique_together': {('type', 'order')},
            },
        ),
    ]
