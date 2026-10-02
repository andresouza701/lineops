(function () {
    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    function setRequired(field, isRequired) {
        if (!field) {
            return;
        }
        if (isRequired) {
            field.setAttribute("required", "required");
        } else {
            field.removeAttribute("required");
        }
    }

    function filterSelectOptions(select, allowedValues) {
        if (!select) {
            return;
        }
        var currentValue = select.value;
        Array.prototype.forEach.call(select.options, function (option) {
            if (option.value === "") {
                option.hidden = false;
                return;
            }
            option.hidden = allowedValues.indexOf(option.value) === -1;
        });
        if (currentValue && allowedValues.indexOf(currentValue) === -1) {
            select.value = "";
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

        var categorySelect = document.getElementById("id_whatsapp_seal_category");
        var planSelect = document.getElementById("id_whatsapp_seal_plan");
        var statusSelect = document.getElementById("id_whatsapp_seal_activation_status");
        var valueInput = document.getElementById("id_whatsapp_seal_monthly_value");
        var emailInput = document.getElementById("id_whatsapp_seal_email");
        var paymentSelect = document.getElementById("id_whatsapp_seal_payment");
        var datesBlock = document.getElementById("seal-dates-fields");
        var activatedOnInput = document.getElementById("id_whatsapp_seal_activated_on");
        var expiresOnInput = document.getElementById("id_whatsapp_seal_expires_on");
        var priceReferenceEl = document.getElementById("seal-price-reference");
        var catalogDataEl = document.getElementById("seal-catalog-data");

        var catalog = [];
        if (catalogDataEl) {
            try {
                catalog = JSON.parse(catalogDataEl.textContent) || [];
            } catch (e) {
                catalog = [];
            }
        }

        function categoriesForSeal(seal) {
            var seen = {};
            var result = [];
            catalog.forEach(function (entry) {
                if (entry.seal === seal && !seen[entry.category]) {
                    seen[entry.category] = true;
                    result.push(entry.category);
                }
            });
            return result;
        }

        function plansForSealCategory(seal, category) {
            return catalog
                .filter(function (entry) {
                    return entry.seal === seal && entry.category === category;
                })
                .map(function (entry) {
                    return entry.plan;
                });
        }

        function priceReferenceFor(seal, category, plan) {
            var match = catalog.filter(function (entry) {
                return entry.seal === seal && entry.category === category && entry.plan === plan;
            })[0];
            return match ? match.price_reference : "";
        }

        function updatePriceReference() {
            if (!priceReferenceEl) {
                return;
            }
            var reference = priceReferenceFor(
                sealSelect.value,
                categorySelect ? categorySelect.value : "",
                planSelect ? planSelect.value : ""
            );
            if (reference) {
                priceReferenceEl.hidden = false;
                priceReferenceEl.textContent = "Referência de preço: " + reference;
            } else {
                priceReferenceEl.hidden = true;
                priceReferenceEl.textContent = "";
            }
        }

        function sync() {
            var hasSeal = !!sealSelect.value;

            detailsBlock.hidden = !hasSeal;
            if (emptyHint) {
                emptyHint.hidden = hasSeal;
            }

            setRequired(categorySelect, hasSeal);
            setRequired(planSelect, hasSeal);
            setRequired(statusSelect, hasSeal);
            setRequired(valueInput, hasSeal);
            setRequired(emailInput, hasSeal);
            setRequired(paymentSelect, hasSeal);

            if (hasSeal && categorySelect) {
                filterSelectOptions(categorySelect, categoriesForSeal(sealSelect.value));
            }
            if (hasSeal && planSelect) {
                filterSelectOptions(
                    planSelect,
                    plansForSealCategory(sealSelect.value, categorySelect ? categorySelect.value : "")
                );
            }

            var isActive = hasSeal && statusSelect && statusSelect.value === "ACTIVE";
            if (datesBlock) {
                datesBlock.hidden = !isActive;
            }
            setRequired(activatedOnInput, isActive);
            setRequired(expiresOnInput, isActive);

            updatePriceReference();
        }

        sealSelect.addEventListener("change", sync);
        if (categorySelect) {
            categorySelect.addEventListener("change", sync);
        }
        if (statusSelect) {
            statusSelect.addEventListener("change", sync);
        }
        if (planSelect) {
            planSelect.addEventListener("change", updatePriceReference);
        }

        sync();
    });
})();
