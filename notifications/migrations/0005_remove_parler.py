# Generated by Django 3.1 on 2020-10-08 10:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0004_migrate_translations'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='notificationtemplatetranslation',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='notificationtemplatetranslation',
            name='master',
        ),
        migrations.DeleteModel(
            name='ContentBlockTranslation',
        ),
        migrations.DeleteModel(
            name='NotificationTemplateTranslation',
        ),
        migrations.RenameField(
            model_name='contentblock',
            old_name='content_t',
            new_name='content',
        ),
        migrations.RenameField(
            model_name='contentblock',
            old_name='name_t',
            new_name='name',
        ),
        migrations.RenameField(
            model_name='notificationtemplate',
            old_name='html_body_t',
            new_name='html_body',
        ),
        migrations.RenameField(
            model_name='notificationtemplate',
            old_name='subject_t',
            new_name='subject',
        ),
    ]
