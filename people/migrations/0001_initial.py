# Generated by Django 3.1.5 on 2021-09-28 21:37

from django.db import migrations, models
import django.db.models.deletion
import image_cropping.fields
import people.models
import wagtail.search.index


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('orgs', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(max_length=100, verbose_name='first name')),
                ('last_name', models.CharField(max_length=100, verbose_name='last name')),
                ('email', models.EmailField(max_length=254, verbose_name='email address')),
                ('title', models.CharField(blank=True, max_length=100, null=True, verbose_name='title')),
                ('postal_address', models.TextField(blank=True, max_length=100, null=True, verbose_name='postal address')),
                ('participated_in_training', models.BooleanField(default=False, help_text='Set to keep track who have attended training sessions', null=True, verbose_name='participated in training')),
                ('image', models.ImageField(blank=True, height_field='image_height', upload_to=people.models.image_upload_path, verbose_name='image', width_field='image_width')),
                ('image_cropping', image_cropping.fields.ImageRatioField('image', '1280x720', adapt_rotation=False, allow_fullsize=False, free_crop=False, help_text=None, hide_image_field=False, size_warning=False, verbose_name='image cropping')),
                ('image_height', models.PositiveIntegerField(editable=False, null=True)),
                ('image_width', models.PositiveIntegerField(editable=False, null=True)),
                ('avatar_updated_at', models.DateTimeField(editable=False, null=True)),
                ('organization', models.ForeignKey(help_text="What is this person's organization", on_delete=django.db.models.deletion.PROTECT, related_name='people', to='orgs.organization', verbose_name='organization')),
            ],
            options={
                'verbose_name': 'person',
                'verbose_name_plural': 'people',
                'ordering': ('last_name', 'first_name'),
            },
            bases=(wagtail.search.index.Indexed, models.Model),
        ),
    ]
