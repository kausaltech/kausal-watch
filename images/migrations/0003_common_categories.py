# Generated by Django 3.2.13 on 2022-05-19 20:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('images', '0002_auto_20210929_0037'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aplansimage',
            name='alt_text',
            field=models.CharField(blank=True, max_length=254, verbose_name='Alt text'),
        ),
        migrations.AlterField(
            model_name='aplansimage',
            name='image_credit',
            field=models.CharField(blank=True, max_length=254, verbose_name='Image byline or credits'),
        ),
    ]
