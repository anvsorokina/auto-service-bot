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

// ====== Hamburger / Sidebar ======

function openSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.add('sidebar-open');
    if (overlay) overlay.classList.add('active');
    document.body.style.overflow = 'hidden'; // prevent background scroll
}

function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('sidebar-open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
}

// Close sidebar with Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeSidebar();
    }
});

// Restore scroll lock state and sidebar on resize
// (prevents a locked body if user resizes from mobile to desktop with sidebar open)
window.addEventListener('resize', function() {
    if (window.innerWidth > 768) {
        closeSidebar();
    }
});

// Flash messages auto-dismiss after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    // Set correct theme toggle icon on load
    var theme = document.documentElement.getAttribute('data-theme') || 'light';
    var btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';

    // Auto-dismiss alerts
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.3s';
            setTimeout(function() { alert.remove(); }, 300);
        }, 5000);
    });

    // Wrap bare data-tables in a scroll container on mobile viewports.
    // This handles tables rendered by HTMX partials that are already in the DOM.
    wrapTablesForMobile();
});

// ====== Table scroll wrapper ======
// Wraps any .data-table that is NOT already inside a .table-scroll-wrapper.

function wrapTablesForMobile() {
    document.querySelectorAll('.data-table').forEach(function(table) {
        if (!table.closest('.table-scroll-wrapper')) {
            var wrapper = document.createElement('div');
            wrapper.className = 'table-scroll-wrapper';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        }
    });
}

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

    // Wrap any newly injected tables
    wrapTablesForMobile();
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
