(function () {
    const metricEls = Array.from(document.querySelectorAll("[data-live-metric]"));
    const pick = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

    const updateMetrics = () => {
        metricEls.forEach((el) => {
            const base = parseInt(el.textContent || el.dataset.base || "0", 10);
            const delta = pick(-1, 3);
            const next = Math.max(0, base + delta);
            el.textContent = String(next);
            el.dataset.base = String(next);
        });
    };

    const drawTrend = (canvas, points) => {
        if (!canvas || !points || points.length === 0) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const width = canvas.width;
        const height = canvas.height;
        const pad = 8;
        const min = Math.min(...points);
        const max = Math.max(...points);
        const range = max - min || 1;

        ctx.clearRect(0, 0, width, height);
        ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, height - pad);
        ctx.lineTo(width, height - pad);
        ctx.stroke();

        ctx.lineWidth = 2;
        ctx.strokeStyle = "#7c3aed";
        ctx.beginPath();

        points.forEach((value, index) => {
            const x = pad + (index * (width - pad * 2)) / Math.max(points.length - 1, 1);
            const y = height - pad - ((value - min) / range) * (height - pad * 2);
            if (index === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
    };

    const parseTrendPoints = () => {
        const el = document.getElementById("trend-points");
        if (!el) return {};
        try {
            return JSON.parse(el.textContent);
        } catch {
            return {};
        }
    };

    const trendData = parseTrendPoints();
    document.querySelectorAll("[data-trend-canvas]").forEach((canvas) => {
        const key = canvas.dataset.trendKey;
        const points = Array.isArray(trendData[key]) ? trendData[key] : [];
        drawTrend(canvas, points);
    });

    if (metricEls.length) {
        setInterval(updateMetrics, 5000);
    }
})();
