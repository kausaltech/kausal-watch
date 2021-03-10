(function() {
  window.$ = window.jQuery;
  window.yl = {jQuery: window.jQuery};
  $(document).ready(function () {
    var selectElements = $('.changelist-filter').children(':has([data-autocomplete-light-url])');
    selectElements.wrap('<form></form>'); // required for forward func
});
})();
