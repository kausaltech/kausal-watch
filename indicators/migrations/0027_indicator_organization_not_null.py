# Generated by Django 3.1.7 on 2021-03-09 11:29

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('django_orghierarchy', '0010_update_tree_fields'),
        ('indicators', '0026_indicator_min_and_max_values'),
    ]

    operations = [
        migrations.AlterField(
            model_name='indicator',
            name='max_value',
            field=models.FloatField(blank=True, help_text='What is the maximum value this indicator can reach? It is used in visualizations as the Y axis maximum.', null=True, verbose_name='maximum value'),
        ),
        migrations.AlterField(
            model_name='indicator',
            name='min_value',
            field=models.FloatField(blank=True, help_text='What is the minimum value this indicator can reach? It is used in visualizations as the Y axis minimum.', null=True, verbose_name='minimum value'),
        ),
        migrations.AlterField(
            model_name='indicator',
            name='organization',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='indicators', to='django_orghierarchy.organization', verbose_name='organization'),
        ),
    ]
