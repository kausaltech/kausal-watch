from __future__ import annotations

from django.db.migrations.operations.models import ModelOptionOperation


class SetModelBasesOptionOperation(ModelOptionOperation):
    """
    Update the bases of a model.

    This can be used to separate a model from its parent.
    """

    def __init__(self, name, bases):
        super().__init__(name)
        self.bases = bases

    def deconstruct(self):
        return (self.__class__.__qualname__, [], {'bases': self.bases})

    def state_forwards(self, app_label, state):
        model_state = state.models[app_label, self.name_lower]
        model_state.bases = self.bases
        state.reload_model(app_label, self.name_lower, delay=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return f'Update bases of the model {self.name}'

    @property
    def migration_name_fragment(self):
        return f'set_{self.name_lower}_bases'
