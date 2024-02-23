document.addEventListener("DOMContentLoaded", function () {
  var button = document.querySelector(
    "button.button.button-small.button-secondary.chooser__choose-button#id_links-ADD"
  );
  if (button) {
    button.setAttribute("aria-label", "Add external link button");
  }
});
