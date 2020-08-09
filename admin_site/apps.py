from django.contrib.admin.apps import AdminConfig
from django.apps import AppConfig


_wagtail_collection_save_instance = None


def collection_save_instance(self):
    print('my save instance')
    instance = self.form.save(commit=False)
    plan = self.request.user.get_active_admin_plan()
    plan.root_collection.add_child(instance=instance)
    return instance


class AdminSiteConfig(AdminConfig):
    default_site = 'admin_site.admin.AplansAdminSite'

    def ready(self):
        super().ready()
        # monkeypatch collection create to make new collections as children
        # of root collection of the currently selected plan
        global _wagtail_collection_save_instance
        if _wagtail_collection_save_instance is None:
            from wagtail.admin.views.collections import Create
            _wagtail_collection_save_instance = Create.save_instance
            Create.save_instance = collection_save_instance

        # from wagtail.core import permissions
        # permissions.collection_permission_policy = 


class AdminSiteStatic(AppConfig):
    name = 'admin_site'
