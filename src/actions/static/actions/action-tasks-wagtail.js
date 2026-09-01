// Whenever the state of an action task is changed, show or hide the 'completed at' field
const selectSelector = 'select[id^="id_tasks-"][id$="-state"]';
function changeCompletedAt() {
    $(selectSelector).each(function () {
        const state = $(this).val();
        const $card = $(this).closest('div[class~="condensed-inline-panel__card"]')
        const $completedAt = $card.find('input[id^="id_tasks-"][id$="-completed_at"]');
        const $completedAtListItem = $completedAt.closest('li');
        if (state === 'completed') {
            $completedAtListItem.show();
        } else {
            $completedAtListItem.hide();
            $completedAt.val('');
        }
    });
}

$(document).on("change", selectSelector, changeCompletedAt);

// The same after creating the form
const selector = 'li[class~="condensed-inline-panel__action-edit"], button[class~="condensed-inline-panel__top-add-button"]'
$(document).on('click', selector, function (ev) {
    setTimeout(function () {
        changeCompletedAt();
    }, 0);
});
