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
})();
