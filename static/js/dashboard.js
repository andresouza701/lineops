(function () {
    const metricEls = Array.from(document.querySelectorAll("[data-live-metric]"));
    const progressEls = Array.from(document.querySelectorAll("[data-live-progress]"));
    const lineCards = Array.from(document.querySelectorAll("[data-line-select]"));

    const inspector = document.getElementById("line-inspector");
    const closeInspectorBtn = document.querySelector("[data-close-inspector]");
    const inspectorLabel = document.querySelector("[data-inspector-label]");
    const inspectorCount = document.querySelector("[data-inspector-count]");
    const inspectorHealth = document.querySelector("[data-inspector-health]");
    const inspectorLatency = document.querySelector("[data-inspector-latency]");
    const inspectorLogs = document.querySelector("[data-inspector-logs]");
    const inspectorBackdrop = document.querySelector("[data-inspector-backdrop]");

    const pick = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

    const renderInspectorLogs = (lineLabel) => {
        if (!inspectorLogs) return;

        const now = new Date();
        const hhmmss = now.toLocaleTimeString("pt-BR", { hour12: false });
        const logs = [
            `[${hhmmss}] Sync de roteamento para ${lineLabel} concluído`,
            `[${hhmmss}] Telemetria recebida sem perda de pacote`,
            `[${hhmmss}] SLA operacional dentro do esperado`,
        ];
        inspectorLogs.innerHTML = logs.map((item) => `<li>${item}</li>`).join("");
    };

    const openInspector = (card) => {
        if (!inspector || !card) return;

        lineCards.forEach((item) => {
            item.classList.remove("is-selected");
            item.setAttribute("aria-expanded", "false");
        });
        card.classList.add("is-selected");
        card.setAttribute("aria-expanded", "true");
        inspector.classList.add("is-open");
        if (inspectorBackdrop) inspectorBackdrop.classList.add("is-open");

        const label = card.dataset.lineLabel || "Linha";
        const count = parseInt(card.dataset.lineCount || "0", 10);
        const health = parseInt(card.dataset.lineHealth || "0", 10);

        if (inspectorLabel) inspectorLabel.textContent = label;
        if (inspectorCount) inspectorCount.textContent = String(count);
        if (inspectorHealth) inspectorHealth.textContent = `${health}%`;
        if (inspectorLatency) inspectorLatency.textContent = `${pick(12, 78)} ms`;
        renderInspectorLogs(label);
    };

    lineCards.forEach((card) => {
        card.addEventListener("click", () => openInspector(card));
        card.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openInspector(card);
            }
        });
    });

    const closeInspector = () => {
        if (!inspector) return;
        inspector.classList.remove("is-open");
        if (inspectorBackdrop) inspectorBackdrop.classList.remove("is-open");
        lineCards.forEach((item) => {
            item.classList.remove("is-selected");
            item.setAttribute("aria-expanded", "false");
        });
    };

    if (closeInspectorBtn) closeInspectorBtn.addEventListener("click", closeInspector);
    if (inspectorBackdrop) inspectorBackdrop.addEventListener("click", closeInspector);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeInspector();
    });

    const updateMetrics = () => {
        metricEls.forEach((el) => {
            const base = parseInt(el.textContent || el.dataset.base || "0", 10);
            const delta = pick(-1, 3);
            const next = Math.max(0, base + delta);
            el.textContent = String(next);
            el.dataset.base = String(next);
        });
    };

    const updateProgress = () => {
        progressEls.forEach((bar) => {
            const current = parseInt(bar.style.width || "0", 10);
            const jitter = pick(-8, 7);
            const next = Math.min(100, Math.max(4, current + jitter));
            bar.style.width = `${next}%`;

            if (next <= 30) {
                bar.style.background = "linear-gradient(90deg, #ef4444, #f59e0b)";
                return;
            }
            if (next <= 60) {
                bar.style.background = "linear-gradient(90deg, #f59e0b, #7c3aed)";
                return;
            }
            bar.style.background = "linear-gradient(90deg, #10b981, #7c3aed)";
        });
    };

    if (metricEls.length || progressEls.length) {
        setInterval(() => {
            updateMetrics();
            updateProgress();
        }, 5000);
    }

    if (lineCards.length > 0) openInspector(lineCards[0]);
})();
