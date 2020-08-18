(function() {
  function initUnsavedChangesNotification() {
    // Store form state at page load
    var form = $('#content-main > form');

    if (!form.length)
      return;

    var initial_form_state = form.serialize();
    //console.log(initial_form_state);
    var form_submitted = false;

    // Store form state after form submit
    $(form).submit(function() {
      console.log('form submitted');
      form_submitted = true;
    });

    // Check form changes before leaving the page and warn user if needed
    $(window).bind('beforeunload', function(e) {
      if (form_submitted)
        return;

      if (typeof(window.CKEDITOR) !== 'undefined') {
        for (var instanceName in window.CKEDITOR.instances) {
          var instance = window.CKEDITOR.instances[instanceName];
          if (instance.checkDirty()) {
            instance.updateElement();
          }
        }
      }

      var form_state = form.serialize();
      if (initial_form_state != form_state) {
        var message = "You have unsaved changes on this page.";
        e.returnValue = message; // Cross-browser compatibility (src: MDN)
        return message;
      }
    });
  }
  function onload() {
    // Fix references to global jQuery objects
    if (!window.$)
      window.$ = django.jQuery;
    if (!window.jQuery)
      window.jQuery = django.jQuery;

    initUnsavedChangesNotification();
  }

  if (!window.django) window.django = {};
  window.django.jQuery = jQuery;

  if (document.readyState !== 'loading'){
    onload();
  } else {
    document.addEventListener('DOMContentLoaded', onload);
  }
})();
