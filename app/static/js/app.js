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
