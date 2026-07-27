// Counselor Assistant - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Mobile sidebar toggle
    const menuToggle = document.querySelector('.menu-toggle');
    const sidebar = document.querySelector('.sidebar');
    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
        document.addEventListener('click', (e) => {
            if (!sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    // Auto-dismiss alerts after 5 seconds
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Auto-calculate duration from start/end time
    const startTime = document.getElementById('start_time');
    const endTime = document.getElementById('end_time');
    const duration = document.getElementById('duration_minutes');
    if (startTime && endTime && duration) {
        function calcDuration() {
            if (startTime.value && endTime.value) {
                const start = new Date('2000-01-01T' + startTime.value);
                const end = new Date('2000-01-01T' + endTime.value);
                const mins = Math.round((end - start) / 60000);
                if (mins > 0) duration.value = mins;
            }
        }
        startTime.addEventListener('change', calcDuration);
        endTime.addEventListener('change', calcDuration);
    }

    // Dynamic category loading for activity log
    const serviceTypeSelect = document.getElementById('service_type');
    const categorySelect = document.getElementById('category');
    if (serviceTypeSelect && categorySelect && window.CATEGORIES) {
        serviceTypeSelect.addEventListener('change', function() {
            const cats = window.CATEGORIES[this.value] || [];
            categorySelect.innerHTML = '<option value="">-- Select Category --</option>';
            cats.forEach(([val, label]) => {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = label;
                categorySelect.appendChild(opt);
            });
        });
    }

    // Confirm delete actions
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!confirm(this.dataset.confirm || 'Are you sure?')) {
                e.preventDefault();
            }
        });
    });

    // Print button
    document.querySelectorAll('.btn-print').forEach(btn => {
        btn.addEventListener('click', () => window.print());
    });

    // Session timeout warning (25 min)
    let sessionTimer;
    function resetSessionTimer() {
        clearTimeout(sessionTimer);
        sessionTimer = setTimeout(() => {
            if (confirm('Your session will expire soon due to inactivity. Continue working?')) {
                fetch('/').then(() => resetSessionTimer());
            }
        }, 25 * 60 * 1000);
    }
    resetSessionTimer();
    ['click', 'keypress', 'scroll'].forEach(evt =>
        document.addEventListener(evt, resetSessionTimer, { passive: true })
    );
});

/* Open Synergy in a new tab and copy the student's ID to the clipboard.
   Buttons opt in via data-synergy-url and data-student-id attributes. */
window.openInSynergy = function(btn) {
    var url = btn.dataset.synergyUrl;
    var studentId = btn.dataset.studentId;
    if (!url || !studentId) return;
    var copied = false;
    var finish = function() {
        window.open(url, '_blank', 'noopener');
        showSynergyToast(copied
            ? ('Synergy ID ' + studentId + ' copied. In Synergy: Ctrl+K → "Student Conference" → Ctrl+F → paste.')
            : ('Could not copy automatically. Student ID is ' + studentId + '.'));
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(studentId).then(function(){ copied = true; finish(); }, finish);
    } else {
        var ta = document.createElement('textarea');
        ta.value = studentId; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { copied = document.execCommand('copy'); } catch(e) {}
        document.body.removeChild(ta);
        finish();
    }
};

function showSynergyToast(msg) {
    var existing = document.getElementById('synergy-toast');
    if (existing) existing.remove();
    var toast = document.createElement('div');
    toast.id = 'synergy-toast';
    toast.textContent = msg;
    toast.style.cssText = 'position:fixed;bottom:24px;right:24px;background:var(--text);color:#fff;' +
        'padding:12px 16px;border-radius:8px;font-size:0.86rem;max-width:380px;line-height:1.4;' +
        'box-shadow:0 8px 30px rgba(0,0,0,0.25);z-index:10000;opacity:0;transition:opacity 0.2s;';
    document.body.appendChild(toast);
    requestAnimationFrame(function(){ toast.style.opacity = '1'; });
    setTimeout(function(){ toast.style.opacity = '0'; setTimeout(function(){ toast.remove(); }, 250); }, 4500);
}

/* Copy a shareable link (e.g. a post-grad self-report link) to the clipboard,
   with a textarea fallback for browsers/contexts without Clipboard API access. */
window.copyLink = function(btn, url) {
    var orig = btn.textContent;
    var done = function() {
        btn.textContent = 'Copied!';
        setTimeout(function() { btn.textContent = orig; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function() { prompt('Copy this link:', url); });
    } else {
        prompt('Copy this link:', url);
    }
};
