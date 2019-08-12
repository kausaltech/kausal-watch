from django.contrib import admin
from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    fields = ('first_name', 'last_name', 'email', 'organization')
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)
