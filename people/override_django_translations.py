# coding: utf-8
_ = lambda s: s
django_standard_messages_to_override = [
    # This can be removed once wagtail.snippets.views.snippets.DeleteView.get_success_message
    # and wagtail_modeladmin.views.DeleteView.post do not share the same
    # msgid anymore
    _("%(model_name)s '%(object)s' deleted.")
]
