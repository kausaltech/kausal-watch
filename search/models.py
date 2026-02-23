from __future__ import annotations

from functools import lru_cache
from typing import Any, Self, cast

from django.db import models
from django.db.models.query_utils import Q

from modelsearch.index import Indexed

from aplans.utils import PlanRelatedModel, PlanRelatedModelQuerySet, RestrictedVisibilityModel


def matches_language(language: str, primary_language: str | None = None, other_languages: list[str] | None = None) -> bool:
    def strip_region(lang: str) -> str:
        lang = lang.split('-', maxsplit=1)[0]
        lang = lang.split('_', maxsplit=1)[0]
        return lang
    languages: list[str] = []
    if primary_language:
        languages.append(strip_region(primary_language))
    if other_languages:
        languages.extend(strip_region(ol) for ol in other_languages)
    return language in languages


@lru_cache
def get_supported_variants(language: str) -> list[str]:
    from django.conf import settings

    variants = []
    for lang, _name in settings.LANGUAGES:
        if matches_language(language, lang):
            variants.append(lang)
    return variants


class SearchableModel[QS: models.QuerySet[Any] = models.QuerySet[Any]](Indexed):
    @classmethod
    def filter_for_language(cls, qs: QS, language: str | None) -> QS:
        if isinstance(qs, PlanRelatedModelQuerySet):
            from actions.models.plan import Plan

            if language is None:
                return qs
            variants = get_supported_variants(language)
            query = Q(primary_language__in=variants)
            query |= Q(other_languages__overlap=variants)
            language_plans = Plan.objects.qs.filter(query)
            return cast('QS', qs.in_plan_qs(language_plans))
        raise NotImplementedError(f'{cls.__name__} does not implement filter_for_language')

    def get_indexed_instance_for_language(self, language: str | None) -> Self | None:
        if isinstance(self, PlanRelatedModel):
            if not language:
                return cast('Self', self)
            plans = self.get_plans()
            for pl in plans:
                if matches_language(language, pl.primary_language, pl.other_languages):
                    return cast('Self', self)
            return None
        raise NotImplementedError(f'{self.__class__.__name__} does not implement get_indexed_instance_for_language')

    @classmethod
    def get_indexed_objects(cls) -> QS:
        from search.context import get_index_language
        language = get_index_language()
        qs = super().get_indexed_objects()
        if issubclass(cls, RestrictedVisibilityModel):
            qs = qs.filter(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        qs = cls.filter_for_language(qs=qs, language=language)
        return qs

    def get_indexed_instance(self) -> Self | None:
        from search.context import get_index_language
        language = get_index_language()
        return self.get_indexed_instance_for_language(language=language)
