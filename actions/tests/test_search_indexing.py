import itertools
import pytest

from actions.models import Action


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('visibility', itertools.product(('draft', 'public'), repeat=2))
def test_action_indexing(graphql_client_query_data, actions_with_relations_factory, visibility):
    draft_actions, public_actions = actions_with_relations_factory(*visibility)
    draft_ids = set(a.id for a in draft_actions)
    public_ids = set(a.id for a in public_actions)
    indexed_actions_qs = Action.get_indexed_objects()
    for a in indexed_actions_qs.all():
        assert a.id not in draft_ids
    for i in public_ids:
        assert indexed_actions_qs.filter(id=i).exists()
