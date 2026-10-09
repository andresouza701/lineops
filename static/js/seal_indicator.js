/* Renderização segura (DOM, sem innerHTML) do indicador de selo
 * compartilhado (SVI-04/05) a partir do dict serializado por
 * telecom.seal_indicator.SealIndicator.as_dict(). Usado por qualquer tela
 * que injete conteúdo dinâmico (AJAX/modal) contendo o indicador, para
 * nunca concatenar texto de selo em innerHTML. */
(function (global) {
    "use strict";

    function createSealIndicatorNode(indicator) {
        if (!indicator || indicator.render_nothing) {
            return null;
        }
        const span = document.createElement("span");
        span.className = `seal-indicator ${indicator.css_class}`;
        if (indicator.show_circle) {
            span.setAttribute("role", "img");
            span.setAttribute("tabindex", "0");
            span.setAttribute("aria-label", indicator.accessible_text);
            span.setAttribute("title", indicator.accessible_text);
            const dot = document.createElement("span");
            dot.className = "seal-indicator__dot";
            dot.setAttribute("aria-hidden", "true");
            span.appendChild(dot);
            const hidden = document.createElement("span");
            hidden.className = "visually-hidden";
            hidden.textContent = indicator.accessible_text;
            span.appendChild(hidden);
        } else {
            span.textContent = indicator.accessible_text;
        }
        return span;
    }

    global.SealIndicator = { createNode: createSealIndicatorNode };
})(window);
