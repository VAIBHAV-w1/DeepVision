/**
 * DeepVision Real-Time Alerts & Notification Toasts
 */
window.DeepVisionNotifications = {
  showToast: function (message, type = 'info') {
    const container = document.getElementById('dv-toast-container');
    if (!container) return;

    const toastEl = document.createElement('div');
    toastEl.className = `alert alert-${type} alert-dismissible fade show shadow-sm mb-2`;
    toastEl.role = 'alert';
    toastEl.innerHTML = `
      <div class="d-flex align-items-center">
        <div>${message}</div>
      </div>
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    container.appendChild(toastEl);
    setTimeout(() => {
      toastEl.classList.remove('show');
      setTimeout(() => toastEl.remove(), 200);
    }, 4500);
  }
};
