from django.contrib import admin
from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    fields = ('first_name', 'last_name', 'email', 'title', 'organization')
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)

    list_display = ('__str__', 'title', 'organization')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.download_avatar()
