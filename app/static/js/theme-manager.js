/**
 * Theme Manager — handles theme switching, persistence, and school color derivation.
 * Themes: light, dark, school, focus, auto
 */
var ThemeManager = (function() {
    'use strict';

    var VALID = ['light', 'dark', 'school', 'focus', 'auto', 'fiesta'];
    var root = document.documentElement;

    // ── Color math helpers (self-contained, no dependencies) ──

    function hexToHSL(hex) {
        hex = hex.replace('#', '');
        var r = parseInt(hex.substring(0, 2), 16) / 255;
        var g = parseInt(hex.substring(2, 4), 16) / 255;
        var b = parseInt(hex.substring(4, 6), 16) / 255;
        var max = Math.max(r, g, b), min = Math.min(r, g, b);
        var h, s, l = (max + min) / 2;
        if (max === min) { h = s = 0; }
        else {
            var d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
            else if (max === g) h = ((b - r) / d + 2) / 6;
            else h = ((r - g) / d + 4) / 6;
        }
        return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
    }

    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        var c = (1 - Math.abs(2 * l - 1)) * s;
        var x = c * (1 - Math.abs((h / 60) % 2 - 1));
        var m = l - c / 2;
        var r, g, b;
        if (h < 60) { r = c; g = x; b = 0; }
        else if (h < 120) { r = x; g = c; b = 0; }
        else if (h < 180) { r = 0; g = c; b = x; }
        else if (h < 240) { r = 0; g = x; b = c; }
        else if (h < 300) { r = x; g = 0; b = c; }
        else { r = c; g = 0; b = x; }
        var toHex = function(v) { var h = Math.round((v + m) * 255).toString(16); return h.length < 2 ? '0' + h : h; };
        return '#' + toHex(r) + toHex(g) + toHex(b);
    }

    function darken(hex, amount) {
        var hsl = hexToHSL(hex);
        return hslToHex(hsl.h, hsl.s, Math.max(0, hsl.l - amount));
    }

    function lighten(hex, amount) {
        var hsl = hexToHSL(hex);
        return hslToHex(hsl.h, hsl.s, Math.min(100, hsl.l + amount));
    }

    // ── Core ──

    function getEffective(theme) {
        if (theme === 'auto') {
            return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        return theme;
    }

    function apply(theme) {
        var effective = getEffective(theme);
        root.dataset.theme = effective;

        // School theme needs dynamic color computation
        if (effective === 'school') {
            applySchoolColors();
        } else {
            // Clear any inline school color overrides
            clearSchoolColors();
        }
    }

    function applySchoolColors() {
        var raw = localStorage.getItem('school_config');
        if (!raw) { root.dataset.theme = 'light'; return; }
        try {
            var cfg = JSON.parse(raw);
            var colors = cfg.colors || {};
            var p = colors.primary || '#2C5F8A';
            var s = colors.secondary || '#E8A838';

            // Contrast safety: if primary is too light, darken it
            var pHSL = hexToHSL(p);
            if (pHSL.l > 60) p = darken(p, pHSL.l - 45);

            root.style.setProperty('--primary', p);
            root.style.setProperty('--primary-light', lighten(p, 15));
            root.style.setProperty('--primary-dark', darken(p, 15));
            root.style.setProperty('--secondary', s);
            root.style.setProperty('--accent', s);
            root.style.setProperty('--bg', lighten(p, 47));
            root.style.setProperty('--border', lighten(p, 40));
            root.style.setProperty('--light-gray', lighten(p, 43));
            root.style.setProperty('--hover-bg', lighten(p, 45));
        } catch (e) {
            root.dataset.theme = 'light';
        }
    }

    function clearSchoolColors() {
        var props = ['--primary', '--primary-light', '--primary-dark', '--secondary',
                     '--accent', '--bg', '--border', '--light-gray', '--hover-bg'];
        for (var i = 0; i < props.length; i++) {
            root.style.removeProperty(props[i]);
        }
    }

    function setTheme(name) {
        if (VALID.indexOf(name) === -1) name = 'light';
        localStorage.setItem('theme_preference', name);
        apply(name);

        // Persist to server
        fetch('/settings/api/theme', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: name, reduced_motion: getReducedMotion() })
        }).catch(function() {});
    }

    function getTheme() {
        return localStorage.getItem('theme_preference') || 'light';
    }

    // ── Reduced motion ──

    function setReducedMotion(enabled) {
        localStorage.setItem('reduced_motion', enabled ? 'true' : 'false');
        root.dataset.reducedMotion = enabled ? 'true' : 'false';

        fetch('/settings/api/theme', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: getTheme(), reduced_motion: enabled })
        }).catch(function() {});
    }

    function getReducedMotion() {
        var stored = localStorage.getItem('reduced_motion');
        if (stored !== null) return stored === 'true';
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    // ── Init ──

    function init() {
        var theme = getTheme();
        apply(theme);

        // Reduced motion
        if (getReducedMotion()) {
            root.dataset.reducedMotion = 'true';
        }

        // Listen for system theme changes (for 'auto' mode)
        try {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
                if (getTheme() === 'auto') apply('auto');
            });
        } catch (e) {}
    }

    // Auto-init on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return {
        setTheme: setTheme,
        getTheme: getTheme,
        setReducedMotion: setReducedMotion,
        getReducedMotion: getReducedMotion,
        init: init
    };
})();
