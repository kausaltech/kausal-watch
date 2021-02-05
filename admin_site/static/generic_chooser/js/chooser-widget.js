function createChooserWidget(id, opts) {
    /*
    id = the ID of the HTML element where chooser behaviour should be attached
    opts = dictionary of configuration options, which may include:
        modalWorkflowResponseName = the response identifier returned by the modal workflow to
            indicate that an item has been chosen. Defaults to 'chosen'.
    */

    opts = opts || {};

    var chooserElement = $('#' + id + '-chooser');
    var docTitle = chooserElement.find('.title');
    var input = $('#' + id);
    var editLink = chooserElement.find('.edit-link');

    function genericChosen(genericData, initial) {
        if (!initial) {
            input.val(genericData.id);
        }
        console.log(genericData);
        input.val(genericData.id);
        docTitle.text(genericData.string);
        chooserElement.removeClass('blank');
        editLink.attr('href', genericData.edit_link);
    }

    $('.action-choose', chooserElement).on('click', function() {
        var responses = {};
        responses[opts.modalWorkflowResponseName || 'chosen'] = genericChosen;

        ModalWorkflow({
            url: chooserElement.data('choose-modal-url'),
            onload: GENERIC_CHOOSER_MODAL_ONLOAD_HANDLERS,
            responses: responses
        });
    });

    $('.action-clear', chooserElement).on('click', function() {
        input.val('');
        chooserElement.addClass('blank');
    });

    if (input.val()) {
        $.ajax(chooserElement.data('choose-modal-url') + encodeURIComponent(input.val()) + '/')
            .done(function (data) {
                genericChosen(data.result, true);
            });
    }
}
