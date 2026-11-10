"""
Thread-safe suppression of modelsearch's per-save reindex for Indicator, for bulk writes.

Every ``Indicator.save()`` otherwise reindexes the indicator in the search backend synchronously
(modelsearch runs the reindex task inline via the immediate task backend). In a bulk write that is
one reindex per row -- including a per-row title-norm recomputation that scans the whole index and,
with Elasticsearch, one round-trip each -- so a bulk category edit over a plan's indicators is
dominated by it. ``disable_indicator_search_auto_update`` turns the per-save reindex off for the
current thread so the bulk write can reindex the affected indicators once afterwards, in a single
batched operation per backend, via ``reindex_indicators``.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import TYPE_CHECKING, Any

from asgiref.local import Local

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_search_auto_update_disabled = Local()


def _search_auto_update_is_disabled() -> bool:
    return getattr(_search_auto_update_disabled, 'value', False)


@contextmanager
def disable_indicator_search_auto_update() -> Iterator[None]:
    """Turn off modelsearch's per-save reindex of Indicator for the current thread."""
    previous = getattr(_search_auto_update_disabled, 'value', False)
    _search_auto_update_disabled.value = True
    try:
        yield
    finally:
        _search_auto_update_disabled.value = previous


def guarded_indicator_search_post_save(instance: Any, **kwargs: Any) -> None:
    """Delegate to modelsearch's handler, unless the reindex is suppressed for this thread."""
    if _search_auto_update_is_disabled():
        return
    from modelsearch.signal_handlers import post_save_signal_handler

    post_save_signal_handler(instance=instance, **kwargs)


def install_search_auto_update_guard() -> None:
    """
    Replace modelsearch's Indicator post_save handler with a thread-suppressible one.

    ``indicators`` loads after ``wagtail.search``, so modelsearch has already connected its handler
    by the time this runs in ``AppConfig.ready``.
    """
    from django.db.models.signals import post_save

    from modelsearch.signal_handlers import post_save_signal_handler

    from indicators.models import Indicator

    post_save.disconnect(post_save_signal_handler, sender=Indicator)
    post_save.connect(guarded_indicator_search_post_save, sender=Indicator, dispatch_uid='indicator_search_guard')


def _index_language_context(language: str | None) -> AbstractContextManager[None]:
    """Set the search index language for a backend's reindex, or leave it unset if it has none."""
    from search.context import set_index_language

    if language is None:
        return nullcontext()
    return set_index_language(language)


def reindex_indicators(pks: Sequence[int]) -> None:
    """
    Reindex the given indicators in every configured search backend, batched and per language.

    ``Indicator.get_indexed_objects()`` is language-aware -- it filters by the current index
    language and to public visibility -- so the indexed set is recomputed inside each backend's
    language context (mirroring ``WatchSearchRebuilder``) rather than once up front; otherwise
    indicators belonging only to another language's plans would be dropped and one language's set
    sent to every backend. Each backend gets its matching set in a single ``add_bulk``, so the
    title-norm recomputation runs once for the batch instead of once per row.

    Indicators that are no longer indexable at all (for example made non-public by the bulk write)
    are deleted from every backend, since the suppressed per-row handler no longer does it. Only
    globally dropped indicators are deleted -- one that merely belongs to a different language is
    still indexed by its own backend and must not be removed from the others.
    """
    from modelsearch.backends import get_search_backends_with_name

    from indicators.models import Indicator

    requested_pks = list(pks)
    if not requested_pks:
        return

    backends = list(get_search_backends_with_name(with_auto_update=True))
    indexed_anywhere: set[int] = set()
    for _name, backend in backends:
        with _index_language_context(getattr(backend, 'language_code', None)):
            objs = list(Indicator.get_indexed_objects().filter(pk__in=requested_pks))
        indexed_anywhere.update(obj.pk for obj in objs)
        if objs:
            backend.add_bulk(Indicator, objs)

    dropped_pks = [pk for pk in requested_pks if pk not in indexed_anywhere]
    if not dropped_pks:
        return
    dropped = list(Indicator.objects.filter(pk__in=dropped_pks))
    for _name, backend in backends:
        for indicator in dropped:
            backend.delete(indicator)
