from django.core.exceptions import ValidationError
from django.forms import ModelChoiceField
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminModelForm


class NodeChoiceField(ModelChoiceField):
    def label_from_instance(self, obj):
        depth_line = '-' * (obj.get_depth() - 1)
        label = super().label_from_instance(obj)
        return f'{depth_line} {label}'


class NodeForm(WagtailAdminModelForm):
    parent = NodeChoiceField(required=False, queryset=None)

    def __init__(self, *args, **kwargs):
        parent_required = kwargs.pop('parent_required', False)
        parent_choices = kwargs.pop('parent_choices', self._meta.model.objects.all())
        super().__init__(*args, **kwargs)
        self.fields['parent'] = NodeChoiceField(required=parent_required, queryset=parent_choices)

        instance = kwargs.get('instance')

        if instance:
            parent = instance.get_parent()
            if parent:
                self.fields['parent'].initial = parent

    def clean_parent(self):
        parent = self.cleaned_data['parent']
        if parent is not None and parent == self.instance:
            raise ValidationError(_("A node cannot be its own parent."), code='invalid_parent')
        return parent

    def save(self, commit=True, *args, **kwargs):
        instance = super().save(commit=False, *args, **kwargs)
        parent = self.cleaned_data['parent']

        if not commit:
            return instance

        if instance.id is None:  # creating a new node
            if parent is None:
                instance = self._meta.model.add_root(instance=instance)
            else:
                instance = parent.add_child(instance=instance)
        else:
            instance.save()
            if instance.get_parent() != parent:
                if parent is None:
                    # Make instance another root
                    previous_root = instance.get_root()
                    instance.move(previous_root, pos='last-sibling')
                else:
                    instance.move(parent, pos='last-child')
                # Need to reload instance after move.
                # Note that instance.refresh_from_db() won't cut it because get_parent() will then still return the old
                # parent if we don't call it with `update=True`.
                # From treebeard docs:
                # django-treebeard uses Django raw SQL queries for some write operations, and raw queries don’t update
                # the objects in the ORM since it’s being bypassed. Because of this, if you have a node in memory and
                # plan to use it after a tree modification (adding/removing/moving nodes), you need to reload it.
                instance = instance._meta.model.objects.get(pk=instance.pk)
                # The following would also seem to work, but is more likely to break.
                # instance.refresh_from_db()
                # instance.get_parent(update=True)
        return instance
