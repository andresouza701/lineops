(function () {
    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    ready(function () {
        var sealSelect = document.getElementById("id_whatsapp_seal");
        var detailsBlock = document.getElementById("seal-detail-fields");
        var emptyHint = document.getElementById("seal-empty-hint");
        var errorSummary = document.getElementById("form-error-summary");

        if (errorSummary) {
            errorSummary.focus();
        }

        if (!sealSelect || !detailsBlock) {
            return;
        }

        var detailFields = detailsBlock.querySelectorAll("input, select, textarea");

        function sync() {
            var hasSeal = !!sealSelect.value;

            detailsBlock.hidden = !hasSeal;
            if (emptyHint) {
                emptyHint.hidden = hasSeal;
            }

            detailFields.forEach(function (field) {
                if (hasSeal) {
                    field.setAttribute("required", "required");
                } else {
                    field.removeAttribute("required");
                }
            });
        }

        sealSelect.addEventListener("change", sync);
        sync();
    });
})();
