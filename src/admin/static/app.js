/**
 * RepairBot Admin Panel — Minimal JavaScript
 * Most interactivity handled by HTMX.
 */

// Flash messages auto-dismiss after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
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
