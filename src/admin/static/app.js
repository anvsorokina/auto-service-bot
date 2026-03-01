/**
 * InGarage AI Admin Panel — JavaScript
 * Most interactivity handled by HTMX.
 */

// ====== Theme Toggle ======
(function() {
    var saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
})();

function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || 'light';
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    var btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
}

// Flash messages auto-dismiss after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    // Set correct theme toggle icon on load
    var theme = document.documentElement.getAttribute('data-theme') || 'light';
    var btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.3s';
            setTimeout(function() { alert.remove(); }, 300);
        }, 5000);
    });
});

// HTMX event handlers
document.body.addEventListener('htmx:afterSwap', function(event) {
    // Re-initialize any dynamic elements after HTMX swaps
    const alerts = event.detail.target.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.3s';
            setTimeout(function() { alert.remove(); }, 300);
        }, 5000);
    });
});

// Confirm dangerous actions
document.addEventListener('click', function(event) {
    const btn = event.target.closest('[data-confirm]');
    if (btn) {
        const message = btn.getAttribute('data-confirm');
        if (!confirm(message)) {
            event.preventDefault();
            event.stopPropagation();
        }
    }
});
