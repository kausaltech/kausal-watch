# Generated by Django 3.0.6 on 2020-08-07 09:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wagtailimages', '0022_uploadedimage'),
        ('actions', '0050_add_supported_languages_to_plan'),
        ('images', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='action',
            name='main_image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.AplansImage'),
        ),
        migrations.AddField(
            model_name='category',
            name='main_image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.AplansImage'),
        ),
        migrations.AddField(
            model_name='plan',
            name='main_image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.AplansImage'),
        ),
    ]
