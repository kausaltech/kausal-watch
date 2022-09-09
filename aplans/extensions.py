# Some ModelAdmins can be disabled if they are replaced in an extension.
disabled_modeladmins = set()


def disable_modeladmin(name):
    disabled_modeladmins.add(name)


def should_register_modeladmin(cls):
    fq_name = '%s.%s' % (cls.__module__, cls.__name__)
    if fq_name in disabled_modeladmins:
        return False
    else:
        return True


def modeladmin_register(cls):
    from wagtail.contrib.modeladmin.options import modeladmin_register as wagtail_modeladmin_register

    if not should_register_modeladmin(cls):
        return cls
    return wagtail_modeladmin_register(cls)
