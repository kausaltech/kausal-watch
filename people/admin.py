from django.contrib import admin
from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)
