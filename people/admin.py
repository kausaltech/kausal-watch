from django.contrib import admin
from image_cropping import ImageCroppingMixin
from .models import Person


@admin.register(Person)
class PersonAdmin(ImageCroppingMixin, admin.ModelAdmin):
    fields = ('first_name', 'last_name', 'email', 'title', 'organization', 'image', 'image_cropping')
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)

    list_display = ('__str__', 'title', 'organization')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.download_avatar()
