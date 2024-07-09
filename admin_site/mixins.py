from typing import Callable


class SuccessUrlEditPageMixin:
    """After editing a model instance, redirect to the edit page again instead of the index page."""
    get_edit_url: Callable

    def get_success_url(self) -> str:
        return self.get_edit_url()

    def get_success_buttons(self) -> list:
        # Remove the button that takes the user to the edit view from the
        # success message, since we're redirecting back to the edit view already
        return []
