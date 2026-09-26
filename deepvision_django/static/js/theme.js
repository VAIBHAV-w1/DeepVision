/**
 * DeepVision Smart Surveillance — Theme Switcher
 * Supports: 'dark', 'light', 'system'
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'deepvision_theme';

  function getSystemTheme() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }

  function getStoredTheme() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const urlTheme = urlParams.get('theme');
      if (urlTheme && ['dark', 'light', 'system'].includes(urlTheme)) {
        return urlTheme;
      }
    } catch (e) {}
    return localStorage.getItem(STORAGE_KEY) || 'dark';
  }

  function applyTheme(preference) {
    const resolvedTheme = preference === 'system' ? getSystemTheme() : preference;
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    document.documentElement.setAttribute('data-theme-pref', preference);

    // Update active state in theme dropdown if present
    document.querySelectorAll('.theme-option').forEach(function (btn) {
      if (btn.getAttribute('data-theme-val') === preference) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Update topbar theme icon
    const themeIcon = document.getElementById('theme-active-icon');
    if (themeIcon) {
      if (resolvedTheme === 'light') {
        themeIcon.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
      } else {
        themeIcon.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
      }
    }
  }

  function setTheme(preference) {
    localStorage.setItem(STORAGE_KEY, preference);
    applyTheme(preference);
  }

  // Initial early apply
  applyTheme(getStoredTheme());

  // Listen for system theme changes if set to 'system'
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (getStoredTheme() === 'system') {
        applyTheme('system');
      }
    });
  }

  // Bind dropdown interactions after DOM ready
  document.addEventListener('DOMContentLoaded', function () {
    const dropdownToggle = document.getElementById('btn-theme-toggle');
    const dropdownMenu = document.getElementById('theme-dropdown-menu');

    if (dropdownToggle && dropdownMenu) {
      dropdownToggle.addEventListener('click', function (e) {
        e.stopPropagation();
        dropdownMenu.classList.toggle('show');
      });

      document.addEventListener('click', function () {
        dropdownMenu.classList.remove('show');
      });
    }

    document.querySelectorAll('.theme-option').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        const pref = this.getAttribute('data-theme-val');
        if (pref) {
          setTheme(pref);
          if (dropdownMenu) dropdownMenu.classList.remove('show');
        }
      });
    });

    applyTheme(getStoredTheme());
  });

  window.DeepVisionTheme = {
    set: setTheme,
    get: getStoredTheme
  };
})();
