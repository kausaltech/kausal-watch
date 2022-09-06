import graphene
from graphene_django.forms.mutation import DjangoModelFormMutation
from graphql import GraphQLResolveInfo
from graphql.error import GraphQLError
from graphql.utilities.ast_to_dict import ast_to_dict

from .graphql_types import AuthenticatedUserNode


def collect_fields(node, fragments):
    """Recursively collects fields from the AST
    Args:
        node (dict): A node in the AST
        fragments (dict): Fragment definitions
    Returns:
        A dict mapping each field found, along with their sub fields.
        {'name': {},
         'sentimentsPerLanguage': {'id': {},
                                   'name': {},
                                   'totalSentiments': {}},
         'slug': {}}
    """

    field = {}

    if node.get('selection_set'):
        for leaf in node['selection_set']['selections']:
            if leaf['kind'] == 'Field':
                field.update({
                    leaf['name']['value']: collect_fields(leaf, fragments)
                })
            elif leaf['kind'] == 'FragmentSpread':
                field.update(collect_fields(fragments[leaf['name']['value']],
                                            fragments))

    return field


def get_fields(info: GraphQLResolveInfo):
    """A convenience function to call collect_fields with info
    Args:
        info (ResolveInfo)
    Returns:
        dict: Returned from collect_fields
    """

    fragments = {}
    node = ast_to_dict(info.field_nodes[0])

    for name, value in info.fragments.items():
        fragments[name] = ast_to_dict(value)

    return collect_fields(node, fragments)


class GraphQLAuthFailedError(GraphQLError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.extensions:
            self.extensions = {
                'code': 'AUTH_FAILED',
            }


class GraphQLAuthRequiredError(GraphQLError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.extensions:
            self.extensions = {
                'code': 'AUTH_REQUIRED',
            }


class CreateModelInstanceMutation(DjangoModelFormMutation, AuthenticatedUserNode):
    # Provide form_class in Meta class of subclass
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, *args, **kwargs):
        # Exclude `id`, otherwise we could change an existing instance by specifying an ID
        kwargs['exclude_fields'] = ['id']
        super().__init_subclass_with_meta__(*args, **kwargs)


class UpdateModelInstanceMutation(DjangoModelFormMutation, AuthenticatedUserNode):
    # Provide form_class in Meta class of subclasses
    class Meta:
        abstract = True

    @classmethod
    def perform_mutate(cls, form, info):
        # Require id in `input` argument, otherwise we could create instances with this mutation
        if form.instance.id is None:
            raise ValueError("ID not specified")
        return super().perform_mutate(form, info)


class DeleteModelInstanceMutation(graphene.Mutation, AuthenticatedUserNode):
    class Arguments:
        id = graphene.ID()

    ok = graphene.Boolean()

    @classmethod
    def __init_subclass_with_meta__(cls, *args, **kwargs):
        cls.model = kwargs.pop('model')
        super().__init_subclass_with_meta__(*args, **kwargs)

    @classmethod
    def mutate(cls, root, info, id):
        obj = cls.model.objects.get(pk=id)
        obj.delete()
        return cls(ok=True)
