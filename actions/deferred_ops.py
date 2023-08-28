from typing import List, Tuple


class DeferredDatabaseOperationsMixin:
    deferred_operations: List[Tuple]
    execute_immediately: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.execute_immediately = True

    def enable_deferred_operations(self):
        self.execute_immediately = False

    def set_deferred_operations(self, operations: List[Tuple]):
        if self.execute_immediately:
            self._execute_immediately(operations)
            return
        self.deferred_operations = operations

    def get_deferred_operations(self) -> List[Tuple]:
        return self.deferred_operations

    def add_deferred_operations(self, operations: List[Tuple]):
        if self.execute_immediately:
            self._execute_immediately(operations)
            return
        try:
            self.deferred_operations.extend(operations)
        except AttributeError:
            self.set_deferred_operations(operations)

    def _execute_immediately(self, operations: List[Tuple]):
        for operation, obj, *rest in operations:
            if operation == 'create':
                obj.save()
            if operation == 'update':
                obj.save()
            if operation == 'delete':
                obj.delete()
            if operation == 'create_and_set_related':
                obj.save()
                operation = 'set_related'
            if operation == 'set_related':
                field_name, related_ids = rest
                setattr(obj, field_name, related_ids)
