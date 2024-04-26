document.addEventListener("DOMContentLoaded", function () {
  const messageContainers = document.querySelectorAll(".messages");
  messageContainers.forEach(function (container) {
    container.setAttribute("role", "alert");
    container.setAttribute("aria-live", "assertive");
    container.setAttribute("aria-atomic", "true");
  });
});