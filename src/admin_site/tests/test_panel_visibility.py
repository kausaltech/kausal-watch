from wagtail.admin.panels import FieldPanel

from admin_site.wagtail import gate_panel_visibility


def test_visible_panel_class_is_returned_unchanged():
    assert gate_panel_visibility(FieldPanel, is_visible=True) is FieldPanel


def test_hidden_panel_class_is_a_cached_subclass():
    hidden = gate_panel_visibility(FieldPanel, is_visible=False)
    assert hidden is not FieldPanel
    assert issubclass(hidden, FieldPanel)
    assert gate_panel_visibility(FieldPanel, is_visible=False) is hidden


def test_hidden_panel_survives_cloning():
    hidden = gate_panel_visibility(FieldPanel, is_visible=False)
    panel = hidden('identifier')
    assert panel.clone().__class__ is hidden


def test_hidden_bound_panel_is_not_shown():
    hidden = gate_panel_visibility(FieldPanel, is_visible=False)
    assert hidden.BoundPanel.is_shown(None) is False  # type: ignore[arg-type]
