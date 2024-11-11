from __future__ import annotations

import graphene
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.models import GraphQLString


class DashboardColumnInterface(graphene.Interface):
    column_label = graphene.String()


class ColumnBlockBase(blocks.StructBlock):
    column_label = blocks.CharBlock(
        required=False, label=_("Label"), help_text=_("Label for the column to be used instead of the default"),
    )

    graphql_fields = [
        GraphQLString('column_label'),
    ]

    graphql_interfaces = (DashboardColumnInterface,)
