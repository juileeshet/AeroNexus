/* Send the CSRF token with every non-GET fetch() call */
(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta || !window.fetch) return;
    var nativeFetch = window.fetch;
    window.fetch = function (url, opts) {
        opts = opts || {};
        var method = (opts.method || 'GET').toUpperCase();
        if (method !== 'GET' && method !== 'HEAD') {
            opts.headers = new Headers(opts.headers || {});
            opts.headers.set('X-CSRF-Token', meta.content);
        }
        return nativeFetch.call(this, url, opts);
    };
})();

// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            alert.style.opacity = '0';
            setTimeout(function() {
                alert.remove();
            }, 500);
        });
    }, 5000);
});

// Form validation
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;

    let isValid = true;
    const requiredFields = form.querySelectorAll('[required]');

    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Password strength indicator
function checkPasswordStrength(password) {
    const strengthBar = document.getElementById('password-strength');
    if (!strengthBar) return;

    const strength = {
        1: 'Very Weak',
        2: 'Weak',
        3: 'Medium',
        4: 'Strong',
        5: 'Very Strong'
    };

    let score = 0;
    if (password.length >= 8) score++;
    if (password.match(/[a-z]/)) score++;
    if (password.match(/[A-Z]/)) score++;
    if (password.match(/[0-9]/)) score++;
    if (password.match(/[^a-zA-Z0-9]/)) score++;

    strengthBar.style.width = `${score * 20}%`;
    strengthBar.textContent = strength[score];
    strengthBar.className = `progress-bar bg-${score > 3 ? 'success' : score > 2 ? 'warning' : 'danger'}`;
}

// Seat selection functionality
function initializeSeatSelection() {
    const seatMap = document.getElementById('seat-map');
    if (!seatMap) return;

    seatMap.addEventListener('click', function(e) {
        if (e.target.classList.contains('seat')) {
            const seats = seatMap.getElementsByClassName('seat');
            Array.from(seats).forEach(seat => seat.classList.remove('selected'));
            e.target.classList.add('selected');
            document.getElementById('selected-seat').value = e.target.dataset.seat;
        }
    });
}

// Initialize all interactive elements
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(tooltip => new bootstrap.Tooltip(tooltip));

    // Initialize seat selection if on booking page
    initializeSeatSelection();

    // Add password strength checker to registration form
    const passwordInput = document.querySelector('input[type="password"]');
    if (passwordInput) {
        passwordInput.addEventListener('input', function() {
            checkPasswordStrength(this.value);
        });
    }
});


/* ---- AeroNexus motion: scroll reveal, count-up numbers, reduced-motion respect ---- */
document.addEventListener('DOMContentLoaded', function () {
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
        document.querySelectorAll('animateMotion').forEach(function (n) { n.remove(); });
    }

    // Count-up numbers: <p data-count="1234" data-prefix="&#8377;" data-suffix="%" data-decimals="1">
    document.querySelectorAll('[data-count]').forEach(function (el) {
        var target = parseFloat(el.dataset.count);
        if (isNaN(target)) return;
        var dec = parseInt(el.dataset.decimals || '0', 10), pre = el.dataset.prefix || '', suf = el.dataset.suffix || '';
        var fmt = function (v) {
            return pre + v.toLocaleString('en-IN', {minimumFractionDigits: dec, maximumFractionDigits: dec}) + suf;
        };
        if (reduce) { el.textContent = fmt(target); return; }
        var start = null, dur = 1100;
        el.textContent = fmt(0);
        requestAnimationFrame(function step(ts) {
            if (start === null) start = ts;
            var p = Math.min((ts - start) / dur, 1);
            el.textContent = fmt(target * (1 - Math.pow(1 - p, 3)));
            if (p < 1) requestAnimationFrame(step);
        });
    });

    // Reveal cards as they scroll into view
    if (reduce || !('IntersectionObserver' in window)) return;
    var selector = '.card, .stat-card, .step, .route-card, .empty-state, .status-banner';
    var items = Array.prototype.filter.call(document.querySelectorAll(selector), function (el) {
        return !el.closest('.modal') && !el.closest('.sky') && !el.closest('.aircraft') && !el.hasAttribute('data-no-reveal');
    });
    var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var el = entry.target;
            el.classList.add('is-visible');
            io.unobserve(el);
            setTimeout(function () { el.style.removeProperty('--reveal-delay'); }, 1400);
        });
    }, {threshold: 0.08, rootMargin: '0px 0px -30px 0px'});
    items.forEach(function (el, i) {
        el.style.setProperty('--reveal-delay', (i % 6) * 70 + 'ms');
        el.setAttribute('data-reveal', '');
        io.observe(el);
    });
});
