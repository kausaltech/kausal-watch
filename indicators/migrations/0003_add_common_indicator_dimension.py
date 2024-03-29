# Generated by Django 3.2.9 on 2022-01-10 15:05

import aplans.utils
from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0007_categorytype_select_widget'),
        ('orgs', '0004_create_organization_admin'),
        ('indicators', '0002_auto_20210929_0037'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commonindicator',
            name='identifier',
            field=aplans.utils.IdentifierField(blank=True, max_length=50, validators=[aplans.utils.IdentifierValidator()], verbose_name='identifier'),
        ),
        migrations.AlterField(
            model_name='indicator',
            name='categories',
            field=models.ManyToManyField(blank=True, related_name='indicators', to='actions.Category'),
        ),
        migrations.AlterField(
            model_name='indicator',
            name='common',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='indicators', to='indicators.commonindicator', verbose_name='common indicator'),
        ),
        migrations.AlterField(
            model_name='indicator',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='indicators', to='orgs.organization', verbose_name='organization'),
        ),
        migrations.CreateModel(
            name='CommonIndicatorDimension',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('common_indicator', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='dimensions', to='indicators.commonindicator')),
                ('dimension', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='common_indicators', to='indicators.dimension')),
            ],
            options={
                'verbose_name': 'common indicator dimension',
                'verbose_name_plural': 'common indicator dimensions',
                'ordering': ['common_indicator', 'order'],
                'unique_together': {('common_indicator', 'dimension')},
                'index_together': {('common_indicator', 'order')},
            },
        ),
    ]
