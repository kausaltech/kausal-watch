from django.contrib.admin.apps import AdminConfig
from django.apps import AppConfig


_wagtail_collection_save_instance = None


def collection_save_instance(self):
    instance = self.form.save(commit=False)
    plan = self.request.user.get_active_admin_plan()
    plan.root_collection.add_child(instance=instance)
    return instance


def collection_index_get_queryset(self):
    plan = self.request.user.get_active_admin_plan()
    if plan.root_collection is None:
        return self.model.objects.none()
    else:
        return plan.root_collection.get_descendants(inclusive=False)


class AdminSiteConfig(AdminConfig):
    default_site = 'admin_site.admin.AplansAdminSite'

    def ready(self):
        super().ready()
        # monkeypatch collection create to make new collections as children
        # of root collection of the currently selected plan
        global _wagtail_collection_save_instance
        global _wagtail_collection_index_get_queryset

        if _wagtail_collection_save_instance is None:
            from wagtail.admin.views.collections import Create, Index
            _wagtail_collection_save_instance = Create.save_instance
            Create.save_instance = collection_save_instance
            Index.get_queryset = collection_index_get_queryset


class AdminSiteStatic(AppConfig):
    name = 'admin_site'
