/**
 * DeepVision Smart Surveillance — Camera Management & Wizard Script
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    // ------------------------------------------------------------------------
    // 1. Camera List Filters (All / Online / Offline / Location)
    // ------------------------------------------------------------------------
    const filterButtons = document.querySelectorAll('.camera-filter-btn');
    const locationSelect = document.getElementById('camera-location-filter');

    function applyFilters() {
      let activeStatus = 'all';
      filterButtons.forEach(function (btn) {
        if (btn.classList.contains('active')) {
          activeStatus = btn.getAttribute('data-status') || 'all';
        }
      });

      const activeLocation = locationSelect ? locationSelect.value.trim().toLowerCase() : '';

      // Filter grid cards
      const cards = document.querySelectorAll('.camera-card');
      cards.forEach(function (card) {
        const status = (card.getAttribute('data-camera-status') || '').toLowerCase();
        const loc = (card.getAttribute('data-camera-location') || '').toLowerCase();

        const matchesStatus = (activeStatus === 'all') || (status === activeStatus);
        const matchesLoc = (!activeLocation) || (loc === activeLocation);

        if (matchesStatus && matchesLoc) {
          card.style.display = '';
        } else {
          card.style.display = 'none';
        }
      });

      // Filter table rows (in camera management view)
      const rows = document.querySelectorAll('.camera-table-row');
      rows.forEach(function (row) {
        const status = (row.getAttribute('data-camera-status') || '').toLowerCase();
        const loc = (row.getAttribute('data-camera-location') || '').toLowerCase();

        const matchesStatus = (activeStatus === 'all') || (status === activeStatus);
        const matchesLoc = (!activeLocation) || (loc === activeLocation);

        if (matchesStatus && matchesLoc) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    }

    if (filterButtons.length > 0) {
      filterButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
          filterButtons.forEach(b => b.classList.remove('active'));
          this.classList.add('active');
          applyFilters();
        });
      });
    }

    if (locationSelect) {
      locationSelect.addEventListener('change', applyFilters);
    }

    // ------------------------------------------------------------------------
    // 2. Add / Edit Camera Source Selection Wizard
    // ------------------------------------------------------------------------
    const sourceOptions = document.querySelectorAll('.source-card-option');
    const sourceTypeInput = document.getElementById('source_type');
    const sourceLabel = document.getElementById('source-label');
    const sourceInput = document.getElementById('source');
    const sourceHelp = document.getElementById('source-help');

    const sourceConfig = {
      phone: {
        label: 'Phone IP Stream URL',
        placeholder: 'http://192.168.1.9:8080/videofeed',
        help: 'Enter the stream address from the IP Webcam mobile application.'
      },
      ip: {
        label: 'IP Camera URL',
        placeholder: 'http://192.168.1.100:8080/stream',
        help: 'Standard HTTP or MJPEG network camera stream address.'
      },
      webcam: {
        label: 'Webcam Index',
        placeholder: '0',
        help: 'Local USB device index (e.g. 0 for default camera, 1 for external).'
      },
      rtsp: {
        label: 'RTSP Stream URL',
        placeholder: 'rtsp://user:pass@192.168.1.50:554/live',
        help: 'Real-Time Streaming Protocol (RTSP) URI from security camera/NVR.'
      },
      video: {
        label: 'Video File Path',
        placeholder: 'videos/sample.mp4',
        help: 'Relative path to an authorized recording video file in videos/ folder.'
      }
    };

    if (sourceOptions.length > 0 && sourceTypeInput) {
      sourceOptions.forEach(function (card) {
        card.addEventListener('click', function () {
          sourceOptions.forEach(c => c.classList.remove('selected'));
          this.classList.add('selected');
          const type = this.getAttribute('data-source-type');
          sourceTypeInput.value = type;

          if (sourceConfig[type]) {
            if (sourceLabel) sourceLabel.textContent = sourceConfig[type].label;
            if (sourceInput) sourceInput.placeholder = sourceConfig[type].placeholder;
            if (sourceHelp) sourceHelp.textContent = sourceConfig[type].help;
          }
        });
      });
    }

    // ------------------------------------------------------------------------
    // 3. Test Connection Button (AJAX)
    // ------------------------------------------------------------------------
    const testBtn = document.getElementById('btn-test-connection');
    const testResult = document.getElementById('connection-status-msg');

    if (testBtn && testResult) {
      testBtn.addEventListener('click', function () {
        const source_type = sourceTypeInput ? sourceTypeInput.value : (document.querySelector('select[name="source_type"]') || {}).value;
        const source = sourceInput ? sourceInput.value.trim() : '';

        if (!source) {
          testResult.className = 'connection-status-msg error';
          testResult.textContent = 'Please enter a camera source before testing.';
          return;
        }

        testBtn.disabled = true;
        testResult.className = 'connection-status-msg';
        testResult.textContent = 'Connecting to camera source...';

        fetch('/api/cameras/test-connection', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-CSRFToken': (window.getCsrfToken ? window.getCsrfToken() : '')
          },
          body: JSON.stringify({
            source_type: source_type,
            source: source
          })
        })
          .then(async function (res) {
            let data;
            try {
              data = await res.json();
            } catch (e) {
              throw new Error('Server returned an invalid response (HTTP ' + res.status + ')');
            }
            if (!res.ok && !data.error && !data.message) {
              throw new Error('Connection test failed with HTTP ' + res.status);
            }
            return data;
          })
          .then(function (data) {
            testBtn.disabled = false;
            if (data.success) {
              testResult.className = 'connection-status-msg success';
              const meta = (data.width && data.height) ? ` (${data.width} × ${data.height}${data.fps ? ' @ ~' + Math.round(data.fps) + ' FPS' : ''})` : '';
              testResult.textContent = '✓ Connection successful' + meta;
            } else {
              testResult.className = 'connection-status-msg error';
              testResult.textContent = '✗ Connection failed: ' + (data.error || data.message || 'Unable to connect to source.');
            }
          })
          .catch(function (err) {
            testBtn.disabled = false;
            testResult.className = 'connection-status-msg error';
            testResult.textContent = '✗ Connection failed: ' + err.message;
          });
      });
    }
  });
})();
