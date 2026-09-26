/**
 * DeepVision Smart Surveillance — Sidebar Navigation
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const sidebar = document.querySelector('.app-sidebar');
    const toggleBtn = document.querySelector('.mobile-nav-toggle');
    const backdrop = document.querySelector('.sidebar-backdrop');

    function openSidebar() {
      if (sidebar) sidebar.classList.add('open');
      if (backdrop) backdrop.classList.add('active');
    }

    function closeSidebar() {
      if (sidebar) sidebar.classList.remove('open');
      if (backdrop) backdrop.classList.remove('active');
    }

    if (toggleBtn) {
      toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (sidebar && sidebar.classList.contains('open')) {
          closeSidebar();
        } else {
          openSidebar();
        }
      });
    }

    if (backdrop) {
      backdrop.addEventListener('click', closeSidebar);
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeSidebar();
    });

    // Mark current active link based on pathname
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar-nav .nav-link');
    navLinks.forEach(function (link) {
      const href = link.getAttribute('href');
      if (href && (href === currentPath || (href !== '/' && currentPath.startsWith(href)))) {
        link.classList.add('active');
      }
    });
  });
})();
