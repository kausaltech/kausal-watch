import os
from django.core.management.base import BaseCommand

from images.models import AplansImage

class Command(BaseCommand):
    help = "Move existing images to the new directory structure"

    def handle(self, *args, **options):
        for image in AplansImage.objects.all():
            old_path = image.file.name
            basename = os.path.basename(old_path)
            new_path = image.file.field.generate_filename(image, basename)
            if old_path != new_path:
                storage = image.file.storage
                try:
                    with storage.open(old_path, 'rb') as source_file:
                        storage.save(new_path, source_file)
                except FileNotFoundError as e:
                    self.stderr.write(self.style.WARNING(f"File not found: {e}; changing path anyway"))
                else:
                    self.stdout.write(f"Deleting {old_path}")
                    storage.delete(old_path)
                image.file.name = new_path
                image.save()

        self.stdout.write(self.style.SUCCESS("Files moved successfully"))
