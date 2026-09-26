/**
 * DeepVision Smart Surveillance — Global Application Script
 */
(function () {
  'use strict';

  // Global CSRF Token accessor for AJAX requests
  window.getCsrfToken = function () {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const match = document.cookie.match(/(?:^|;\s*)(?:deepvision_django_csrftoken|csrftoken)=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  };

  document.addEventListener('DOMContentLoaded', function () {
    // Flash message dismissers
    const alerts = document.querySelectorAll('.alert-banner');
    alerts.forEach(function (alert) {
      const closeBtn = alert.querySelector('.alert-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', function () {
          alert.style.opacity = '0';
          setTimeout(function () {
            alert.remove();
          }, 200);
        });
      }
      // Auto dismiss success alerts after 6 seconds
      if (alert.classList.contains('alert-success')) {
        setTimeout(function () {
          alert.style.opacity = '0';
          setTimeout(function () {
            alert.remove();
          }, 200);
        }, 6000);
      }
    });

    // FAQ Accordion
    const faqItems = document.querySelectorAll('.faq-item');
    faqItems.forEach(function (item) {
      const trigger = item.querySelector('.faq-trigger');
      if (trigger) {
        trigger.addEventListener('click', function () {
          item.classList.toggle('open');
        });
      }
    });

    // Global Topbar Search bar quick filter
    const searchInput = document.getElementById('topbar-search');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        const query = this.value.trim().toLowerCase();
        
        // Filter camera cards if present
        const cameraCards = document.querySelectorAll('.camera-card');
        cameraCards.forEach(function (card) {
          const name = (card.querySelector('.camera-name') || {}).textContent || '';
          const location = (card.querySelector('.camera-location') || {}).textContent || '';
          if (!query || name.toLowerCase().includes(query) || location.toLowerCase().includes(query)) {
            card.style.display = '';
          } else {
            card.style.display = 'none';
          }
        });

        // Filter table rows if present
        const tableRows = document.querySelectorAll('.cctv-table tbody tr');
        tableRows.forEach(function (row) {
          const text = row.textContent.toLowerCase();
          if (!query || text.includes(query)) {
            row.style.display = '';
          } else {
            row.style.display = 'none';
          }
        });
      });
    }

    // =========================================================================
    // Instant Security Alert Popup / Toast Notification Engine (2s Polling)
    // =========================================================================
    (function initAlertToasts() {
      let seenAlertIds = new Set();
      let initialSeedDone = false;

      // Toast container
      let container = document.getElementById('deepvision-toast-container');
      if (!container) {
        container = document.createElement('div');
        container.id = 'deepvision-toast-container';
        container.style.position = 'fixed';
        container.style.top = '1.25rem';
        container.style.right = '1.25rem';
        container.style.zIndex = '999999';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '0.75rem';
        container.style.maxWidth = '400px';
        container.style.width = 'calc(100vw - 2.5rem)';
        container.style.pointerEvents = 'none';
        document.body.appendChild(container);
      }

      function showToast(alertData) {
        if (!alertData) return;
        const toast = document.createElement('div');
        toast.className = 'deepvision-alert-toast';
        toast.style.pointerEvents = 'auto';
        toast.style.background = 'var(--bg-surface-raised, #182230)';
        toast.style.color = 'var(--text-main, #f8fafc)';
        toast.style.border = '1px solid var(--border-color, rgba(255,255,255,0.1))';
        toast.style.borderRadius = '8px';
        toast.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)';
        toast.style.padding = '1rem';
        toast.style.display = 'flex';
        toast.style.flexDirection = 'column';
        toast.style.gap = '0.5rem';
        toast.style.animation = 'slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)';
        toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';

        const severity = (alertData.severity || 'medium').toLowerCase();
        let badgeBg = '#3b82f6';
        let borderColor = 'rgba(59, 130, 246, 0.4)';
        if (severity === 'critical' || severity === 'high') {
          badgeBg = '#ef4444';
          borderColor = 'rgba(239, 68, 68, 0.5)';
        } else if (severity === 'medium') {
          badgeBg = '#f59e0b';
          borderColor = 'rgba(245, 158, 11, 0.4)';
        }
        toast.style.borderLeft = `4px solid ${badgeBg}`;

        toast.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;">
            <div style="display:flex;align-items:center;gap:0.5rem;">
              <span style="background:${badgeBg};color:#fff;font-size:0.65rem;font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px;">
                ${severity}
              </span>
              <span style="font-size:0.8rem;font-weight:600;color:var(--text-muted,#94a3b8);">
                Camera #${alertData.camera_id || 'Live'}
              </span>
            </div>
            <button type="button" class="toast-close-btn" style="background:none;border:none;color:var(--text-muted,#94a3b8);cursor:pointer;font-size:1.1rem;line-height:1;padding:0;" aria-label="Close">
              &times;
            </button>
          </div>
          <div style="font-size:0.9rem;font-weight:700;color:var(--text-main,#f8fafc);line-height:1.3;">
            ${alertData.title || 'Security Anomaly Detected'}
          </div>
          <div style="font-size:0.8rem;color:var(--text-secondary,#cbd5e1);line-height:1.4;">
            ${alertData.message || 'Suspicious behavioral or perimeter trigger observed.'}
          </div>
          <div style="display:flex;justify-content:flex-end;gap:0.5rem;margin-top:0.25rem;">
            <a href="/alerts/${alertData.id}" style="font-size:0.78rem;font-weight:600;color:#38bdf8;text-decoration:none;padding:3px 8px;border-radius:4px;background:rgba(56,189,248,0.1);display:inline-flex;align-items:center;gap:4px;">
              View Alert &rarr;
            </a>
          </div>
        `;

        const closeBtn = toast.querySelector('.toast-close-btn');
        if (closeBtn) {
          closeBtn.addEventListener('click', function () {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            setTimeout(() => toast.remove(), 300);
          });
        }

        container.appendChild(toast);

        // Auto dismiss after 7 seconds
        setTimeout(function () {
          if (toast.parentNode) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            setTimeout(() => toast.remove(), 300);
          }
        }, 7000);
      }

      function pollAlerts() {
        if (document.hidden) return;
        fetch('/api/notifications?status=unread&per_page=5')
          .then(function (r) {
            if (!r.ok) return null;
            return r.json();
          })
          .then(function (data) {
            if (!data || !data.notifications) return;
            
            // On first poll, mark existing as seen so we don't spam toasts
            if (!initialSeedDone) {
              data.notifications.forEach(n => {
                if (n.alert && n.alert.id) seenAlertIds.add(n.alert.id);
              });
              initialSeedDone = true;
              return;
            }

            // Subsequent polls: trigger toast for genuinely new unread alerts
            data.notifications.forEach(n => {
              if (n.alert && n.alert.id && !seenAlertIds.has(n.alert.id)) {
                seenAlertIds.add(n.alert.id);
                showToast(n.alert);
              }
            });
          })
          .catch(function () {});
      }

      // Poll every 2 seconds
      setInterval(pollAlerts, 2000);
      // Run once after 500ms
      setTimeout(pollAlerts, 500);
    })();
  });
})();
