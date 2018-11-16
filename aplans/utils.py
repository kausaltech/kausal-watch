import re


def camelcase_to_underscore(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def register_view_helper(view_list, klass, name=None, base_name=None):
    if not name:
        model = klass.serializer_class.Meta.model
        name = camelcase_to_underscore(model._meta.object_name)

    entry = {'class': klass, 'name': name}
    if base_name is not None:
        entry['base_name'] = base_name

    view_list.append(entry)

    return klass
