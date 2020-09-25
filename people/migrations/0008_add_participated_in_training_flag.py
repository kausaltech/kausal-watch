# Generated by Django 3.1 on 2020-09-25 10:59

from django.db import migrations, models
import people.models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0007_person_main_image'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='person',
            name='main_image',
        ),
        migrations.AddField(
            model_name='person',
            name='participated_in_training',
            field=models.BooleanField(help_text='Set to keep track who have attended training sessions', null=True, verbose_name='participated in training'),
        ),
        migrations.AlterField(
            model_name='person',
            name='image',
            field=models.ImageField(blank=True, height_field='image_height', upload_to=people.models.image_upload_path, verbose_name='image', width_field='image_width'),
        ),
    ]
