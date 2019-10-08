from django.contrib import admin
from .models import User, OrganizationAdmin


class OrganizationAdminAdmin(admin.TabularInline):
    search_fields = ('user',)
    autocomplete_fields = ('organization',)
    model = OrganizationAdmin
    extra = 0


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    search_fields = ('first_name', 'last_name', 'email')
    inlines = [OrganizationAdminAdmin]
