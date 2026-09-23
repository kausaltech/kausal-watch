"""
Rename ``allow_public_site_login`` to ``show_login_link_in_public_ui``.

The flag never governed whether anyone could sign in to the public site — nothing consulted it
on the way in. It governed one thing in the frontend: whether the footer shows a sign-in link.
Signing in is now explicitly available for every plan, so the field is named after the only
question it answers.

As with the previous renames, this is Django model state only: the column keeps the name it was
born with, so pods running the previous release keep working through the deploy.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0195_drop_expose_unpublished_flag'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name='planfeatures',
                    old_name='allow_public_site_login',
                    new_name='show_login_link_in_public_ui',
                ),
                migrations.AlterField(
                    model_name='planfeatures',
                    name='show_login_link_in_public_ui',
                    field=models.BooleanField(
                        default=True,
                        db_column='allow_public_site_login',
                        help_text=(
                            'Should the public website offer a link to sign in? Signing in is always possible; '
                            'some plans simply have no use for the link and would rather not show it.'
                        ),
                        verbose_name='Show the sign-in link in the public UI',
                    ),
                ),
            ],
        ),
    ]
