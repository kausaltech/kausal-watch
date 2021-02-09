from django.core.exceptions import FieldDoesNotExist
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from wagtail.images.rect import Rect

from actions.models import Action, Category, Plan
from images.models import AplansImage


HAS_IMAGE = Q(image__isnull=False) & ~Q(image='')
HAS_MAIN_IMAGE = Q(main_image__isnull=False)


class Command(BaseCommand):
    help = "Migrate image fields to Wagtail images"

    def add_arguments(self, parser):
        parser.add_argument(
            '--migrate-if-file-absent',
            action='store_true',
            help="Mark instances as migrated if their image references a file that does not exist",
        )

    def handle(self, *args, **options):
        migrate_if_file_absent = options.get('migrate_if_file_absent')
        self.migrate_model(Action,
                           lambda action: action.plan.root_collection,
                           migrate_if_file_absent=migrate_if_file_absent)

        def get_category_collection(instance):
            assert len(instance.get_plans()) == 1
            return instance.get_plans()[0].root_collection

        self.migrate_model(Category,
                           get_category_collection,
                           migrate_if_file_absent=migrate_if_file_absent)
        self.migrate_model(Plan,
                           lambda plan: plan.root_collection,
                           migrate_if_file_absent=migrate_if_file_absent)

    @transaction.atomic
    def migrate_instance(self, instance, collection):
        """
        Migrate the model instance's `image` field to its `main_image` field.

        The new image is put in the given collection.
        """
        instance.main_image = AplansImage(
            collection=collection,
            title=instance.name,
        )
        # Crop coordinates
        x1, y1, x2, y2 = tuple(int(s) for s in instance.image_cropping.split(','))
        instance.main_image.set_focal_point(Rect(x1, y1, x2, y2))
        image_copy = ContentFile(instance.image.read())
        image_filename = instance.image.name.split('/')[-1]
        instance.main_image.file.save(image_filename, image_copy)
        instance.image_was_migrated = True
        instance.save()
        self.stdout.write(f"Migrated '{instance.__class__.__name__}' instance '{instance}'.")
        # FIXME: We should now be able to safely call instance.image.delete().
        # Note, however, that this would keep the auto-generated thumbnails.

    def migrate_model(self, model, get_collection, migrate_if_file_absent=False):
        """
        Migrate all instances having an `image` but no `main_image`.

        The new image for an instance `instance` is put in the collection given
        by `get_collection(instance)`.

        If the image file of an instance is missing, an exception is raised,
        unless `migrate_if_file_absent` is True, in which case a warning is
        printed and processing may continue with other instances. Such
        instances will have `image_was_migrated` set to True.
        """
        # Make sure the `image_was_migrated` field is there. If it is not, a FieldDoesNotExist exception is
        # raised. The reason for the field missing is probably that the user has checked out a version of
        # the code where the field has been removed. Setting the field to True would have no effect then.
        try:
            model._meta.get_field('image_was_migrated')
        except FieldDoesNotExist as fe:
            raise FieldDoesNotExist(f"{fe}. Probably you checked out a too recent version of the code.")

        for instance in model.objects.filter(HAS_IMAGE & ~HAS_MAIN_IMAGE):
            try:
                self.migrate_instance(instance, get_collection(instance))
            except FileNotFoundError as e:
                if migrate_if_file_absent:
                    self.stderr.write(f"Marking '{instance.__class__.__name__}' instance '{instance}' as migrated "
                                      f"despite error:")
                    self.stderr.write(str(e))
                    instance.main_image = None
                    instance.image_was_migrated = True
                    instance.save()
                else:
                    raise
