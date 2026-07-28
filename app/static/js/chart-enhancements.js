/* Chart.js enhancement layer — depth, motion, polish.
   Loaded immediately after the Chart.js vendor bundle on every page that uses
   charts. Auto-registers a global plugin and tweaks defaults; individual charts
   need no per-chart changes to benefit.

   Three things this does:
     1. Subtle drop shadow under every dataset (bars, lines, arcs) via canvas
        shadowColor — gives the chart depth without a heavy outline.
     2. Smoother entrance animation with a staggered per-bar delay, so data
        sweeps in left-to-right instead of springing in all at once.
     3. Rounded bar tops + slightly bolder borders so adjacent bars don't
        smear into each other.
*/
(function(){
    if (typeof Chart === 'undefined') return;

    /* ── 1. Subtle drop-shadow plugin ─────────────────────────────────── */
    var subtleShadow = {
        id: 'subtleShadow',
        beforeDatasetDraw: function(chart, args) {
            var meta = chart.getDatasetMeta(args.index);
            // Skip line-chart point markers — shadows look noisy on them.
            // Apply to bars and the line/area stroke itself.
            if (meta.type === 'line') {
                chart.ctx.save();
                chart.ctx.shadowColor = 'rgba(20, 30, 50, 0.18)';
                chart.ctx.shadowBlur = 6;
                chart.ctx.shadowOffsetX = 0;
                chart.ctx.shadowOffsetY = 3;
            } else if (meta.type === 'bar') {
                chart.ctx.save();
                chart.ctx.shadowColor = 'rgba(20, 30, 50, 0.22)';
                chart.ctx.shadowBlur = 8;
                chart.ctx.shadowOffsetX = 0;
                chart.ctx.shadowOffsetY = 4;
            } else if (meta.type === 'doughnut' || meta.type === 'pie') {
                chart.ctx.save();
                chart.ctx.shadowColor = 'rgba(20, 30, 50, 0.18)';
                chart.ctx.shadowBlur = 10;
                chart.ctx.shadowOffsetX = 0;
                chart.ctx.shadowOffsetY = 4;
            }
        },
        afterDatasetDraw: function(chart, args) {
            var meta = chart.getDatasetMeta(args.index);
            if (['line','bar','doughnut','pie'].indexOf(meta.type) !== -1) {
                chart.ctx.restore();
            }
        },
    };
    Chart.register(subtleShadow);

    /* ── 2. Smoother, staggered animation ─────────────────────────────── */
    Chart.defaults.animation = {
        duration: 650,
        easing: 'easeOutQuart',
        /* Per-data-point delay: bars sweep left-to-right, with each dataset
           offset slightly. Only applies on initial draw, not on hover/resize. */
        delay: function(ctx){
            if (ctx.type !== 'data') return 0;
            if (ctx.mode !== 'default') return 0;
            return (ctx.dataIndex || 0) * 22 + (ctx.datasetIndex || 0) * 80;
        },
    };
    Chart.defaults.animations = Chart.defaults.animations || {};
    Chart.defaults.animations.colors = false;   // don't animate color transitions
    Chart.defaults.animations.numbers = { duration: 650, easing: 'easeOutQuart' };

    /* ── 3. Default element styling: rounded bars, bolder borders ─────── */
    Chart.defaults.elements.bar.borderWidth = 1.5;
    Chart.defaults.elements.bar.borderRadius = 4;
    Chart.defaults.elements.bar.hoverBorderWidth = 2.5;
    Chart.defaults.elements.line.borderWidth = 2.5;
    Chart.defaults.elements.point.radius = 3.5;
    Chart.defaults.elements.point.hoverRadius = 6;
    Chart.defaults.elements.arc.borderWidth = 2;

    /* Slightly nicer default font */
    if (Chart.defaults.font) {
        Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";
    }

    /* ── 4. Theme-aware text + grid colours ───────────────────────────────
       Chart.js renders tick labels, legend text, axis titles and grid lines
       on the canvas. It can't read CSS variables — it uses its hardcoded
       grey defaults (#666 text on #fff bg) unless told otherwise. On dark
       themes (dark, focus, glass*) those grey ticks/labels become unreadable.

       Read the current --text and --border tokens from <html> at load time
       and seed Chart.defaults with them. Every chart created after this
       script runs inherits the right colours automatically — no per-chart
       options changes needed across the app. Theme switches take effect on
       next page load (the same model the rest of the theming uses). */
    var rootStyle = getComputedStyle(document.documentElement);
    function tok(name, fallback) {
        var v = (rootStyle.getPropertyValue(name) || '').trim();
        return v || fallback;
    }
    var textColor   = tok('--text',        '#333333');
    var mutedColor  = tok('--text-muted',  textColor);
    var borderColor = tok('--glass-border', tok('--border', 'rgba(127,140,141,0.20)'));

    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = borderColor;
    if (Chart.defaults.plugins) {
        if (Chart.defaults.plugins.legend && Chart.defaults.plugins.legend.labels) {
            Chart.defaults.plugins.legend.labels.color = textColor;
        }
        if (Chart.defaults.plugins.title) {
            Chart.defaults.plugins.title.color = textColor;
        }
        if (Chart.defaults.plugins.tooltip) {
            /* Chart.js's tooltip already uses a dark bubble that reads on every
               theme — leave it alone, just make sure body text is light enough.
               (Default is rgba(255,255,255,0.85) which is fine.) */
        }
    }
    /* Scale-level defaults so every axis picks up the same palette. */
    if (Chart.defaults.scale) {
        if (Chart.defaults.scale.ticks) Chart.defaults.scale.ticks.color = mutedColor;
        if (Chart.defaults.scale.title) Chart.defaults.scale.title.color = textColor;
        if (Chart.defaults.scale.grid) {
            Chart.defaults.scale.grid.color = borderColor;
            Chart.defaults.scale.grid.borderColor = borderColor;
        }
    }
    /* Chart.js 4.x splits scale defaults by type (linear/category/etc.).
       Apply the same colours to each so cartesian and radial axes match. */
    ['linear', 'category', 'time', 'logarithmic', 'radialLinear'].forEach(function(t){
        var s = Chart.defaults.scales && Chart.defaults.scales[t];
        if (!s) return;
        if (s.ticks) s.ticks.color = mutedColor;
        if (s.title) s.title.color = textColor;
        if (s.grid)  { s.grid.color = borderColor; s.grid.borderColor = borderColor; }
        if (s.angleLines) s.angleLines.color = borderColor;
        if (s.pointLabels) s.pointLabels.color = textColor;
    });

    /* ── 5. Shared categorical palette ────────────────────────────────────
       One fixed-order 8-hue palette for identity encodings (donut slices,
       multi-series charts), stepped per light/dark surface and validated for
       adjacent-pair colorblind separation + contrast against both the white
       card surface and the dark/glass panel (#1C1F2E depth). Fixed order is
       the CVD-safety mechanism — assign slots in order, never shuffle or
       cycle; past 8 series, fold the tail into "Other" server-side.
       Mode is picked from the effective --bg luminance so every theme
       (including future ones) gets the right steps without a lookup table. */
    function _lum(hex) {
        var m = /^#([0-9a-f]{6})$/i.exec((hex || '').trim());
        if (!m) return null;
        var n = parseInt(m[1], 16);
        return (0.2126 * (n >> 16 & 255) + 0.7152 * (n >> 8 & 255) + 0.0722 * (n & 255)) / 255;
    }
    var _bgLum = _lum(tok('--bg', '#ffffff'));
    var _theme = document.documentElement.dataset.theme || 'light';
    var _isDark = (_bgLum !== null) ? (_bgLum < 0.45)
                : (_theme === 'dark' || _theme.indexOf('glass') === 0);
    window.chartPalette = _isDark
        ? ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
        : ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
    /* Surface color for slice/segment separators (the "gap" ring between
       donut arcs). Falls back to the old hardcoded white on light themes. */
    window.chartSurface = tok('--surface', _isDark ? '#1C1F2E' : '#ffffff');
})();
