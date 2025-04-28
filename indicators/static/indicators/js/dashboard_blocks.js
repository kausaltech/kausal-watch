document.addEventListener('DOMContentLoaded', function() {

    if (typeof window.ModalWorkflow === 'function') {
        const originalModalWorkflow = window.ModalWorkflow;
        window.ModalWorkflow = function(opts) {
            if (opts.url && opts.url.includes('/admin/dimension-chooser/')) {
                const structBlock = document.activeElement.closest('.struct-block');
                if (structBlock) {
                    const indicatorInput = structBlock.querySelector('.w-field--indicator_chooser input[type="hidden"]');
                    if (indicatorInput && indicatorInput.value) {
                        const url = new URL(opts.url, window.location.href);
                        url.searchParams.set('indicator_id', indicatorInput.value);
                        opts.url = url.toString();
                    }
                }
            }
            return originalModalWorkflow(opts);
        };
    }
});
