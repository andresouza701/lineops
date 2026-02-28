// ClipCraft-inspired dashboard interactivity
(function() {
    // Simulate live update for dashboard metrics
    const updateMetrics = () => {
        document.querySelectorAll('[data-live-metric]').forEach(el => {
            const base = parseInt(el.dataset.base, 10) || 0;
            el.textContent = base + Math.floor(Math.random() * 5);
        });
    };
    setInterval(updateMetrics, 5000);

    // Panel open/close logic
    document.querySelectorAll('[data-panel-toggle]').forEach(btn => {
        btn.addEventListener('click', function() {
            const target = document.getElementById(this.dataset.panelTarget);
            if (target) {
                target.classList.toggle('open');
            }
        });
    });
})();
