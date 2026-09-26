/**
 * DeepVision Smart Surveillance — Live View Stream Monitor
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const streamImg = document.getElementById('camera-live-stream');
    if (!streamImg) return;

    const cameraId = streamImg.getAttribute('data-camera-id');
    const aiStatusVal = document.getElementById('meta-ai-status');
    const recStatusVal = document.getElementById('meta-rec-status');
    const btnRecord = document.getElementById('btn-action-record');
    const modeButtons = document.querySelectorAll('.btn-mode');

    // ------------------------------------------------------------------------
    // 1. Stream Mode Switcher (ORIGINAL / TRACKING + DETECTION)
    // ------------------------------------------------------------------------
    modeButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        modeButtons.forEach(b => b.classList.remove('active'));
        this.classList.add('active');

        const rawMode = (this.getAttribute('data-mode') || 'tracking').toLowerCase();
        const mode = (rawMode === 'raw' || rawMode === 'original') ? 'raw' : 'tracking';
        const targetUrl = `/cameras/${cameraId}/stream?mode=${mode}`;

        // Cleanly reset image source to close previous multipart HTTP connection in Chrome
        streamImg.src = '';
        setTimeout(function () {
          streamImg.src = `${targetUrl}&t=${Date.now()}`;
        }, 40);

        try {
          const url = new URL(window.location.href);
          url.searchParams.set('mode', mode);
          window.history.replaceState(null, '', url.toString());
        } catch (e) {}

        if (aiStatusVal) {
          if (mode === 'detection') {
            aiStatusVal.textContent = 'YOLO11 Active';
          } else if (mode === 'tracking') {
            aiStatusVal.textContent = 'ByteTrack Active';
          } else {
            aiStatusVal.textContent = 'Raw Passthrough';
          }
        }
      });
    });

    // ------------------------------------------------------------------------
    // 2. Snapshot Capture & Download
    // ------------------------------------------------------------------------
    const btnSnapshot = document.getElementById('btn-action-snapshot');
    if (btnSnapshot) {
      btnSnapshot.addEventListener('click', function () {
        btnSnapshot.disabled = true;
        
        const snapshotUrl = `/cameras/${cameraId}/snapshot?t=${Date.now()}`;
        fetch(snapshotUrl)
          .then(function (res) {
            if (!res.ok) throw new Error('Snapshot capture failed');
            return res.blob();
          })
          .then(function (blob) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `camera-${cameraId}-snapshot-${Date.now()}.jpg`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            btnSnapshot.disabled = false;
          })
          .catch(function (err) {
            console.error('Snapshot error:', err);
            // Canvas fallback
            try {
              const canvas = document.createElement('canvas');
              canvas.width = streamImg.naturalWidth || 640;
              canvas.height = streamImg.naturalHeight || 480;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(streamImg, 0, 0);
              const dataURL = canvas.toDataURL('image/jpeg', 0.95);
              const a = document.createElement('a');
              a.href = dataURL;
              a.download = `camera-${cameraId}-snapshot-${Date.now()}.jpg`;
              document.body.appendChild(a);
              a.click();
            } catch (e) {
              alert('Could not download snapshot from active stream.');
            }
            btnSnapshot.disabled = false;
          });
      });
    }

    // ------------------------------------------------------------------------
    // 3. Fullscreen Monitor Toggle
    // ------------------------------------------------------------------------
    const btnFullscreen = document.getElementById('btn-action-fullscreen');
    const monitorCard = document.querySelector('.live-monitor-card');

    if (btnFullscreen && monitorCard) {
      btnFullscreen.addEventListener('click', function () {
        if (!document.fullscreenElement) {
          if (monitorCard.requestFullscreen) {
            monitorCard.requestFullscreen();
          } else if (monitorCard.webkitRequestFullscreen) {
            monitorCard.webkitRequestFullscreen();
          }
        } else {
          if (document.exitFullscreen) {
            document.exitFullscreen();
          }
        }
      });
    }

    // ------------------------------------------------------------------------
    // 4. Start / Stop Recording Control
    // ------------------------------------------------------------------------
    function setRecordingUI(isRecording) {
      if (!btnRecord) return;
      if (isRecording) {
        btnRecord.setAttribute('data-recording', 'true');
        btnRecord.classList.remove('btn-secondary');
        btnRecord.classList.add('btn-danger');
        btnRecord.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg> Stop Recording';
        if (recStatusVal) recStatusVal.textContent = 'Recording Active';
      } else {
        btnRecord.setAttribute('data-recording', 'false');
        btnRecord.classList.remove('btn-danger');
        btnRecord.classList.add('btn-secondary');
        btnRecord.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="6"/></svg> Start Recording';
        if (recStatusVal) recStatusVal.textContent = 'Standby';
      }
    }

    if (btnRecord) {
      btnRecord.addEventListener('click', function () {
        const isRecording = btnRecord.getAttribute('data-recording') === 'true';
        const targetAction = isRecording ? 'stop' : 'start';

        btnRecord.disabled = true;

        fetch(`/cameras/${cameraId}/record/${targetAction}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-CSRFToken': (window.getCsrfToken ? window.getCsrfToken() : '')
          }
        })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            btnRecord.disabled = false;
            const success = data.status === 'ok' || data.status === 'warning' || data.status === 'success' || data.success === true;
            if (success) {
              setRecordingUI(targetAction === 'start');
            } else {
              alert('Recording error: ' + (data.message || data.error || 'Action failed'));
            }
          })
          .catch(function (err) {
            console.error('Recording request error:', err);
            btnRecord.disabled = false;
            alert('Network error while toggling recording.');
          });
      });
    }

    // ------------------------------------------------------------------------
    // 5. Status Telemetry Sync Polling
    // ------------------------------------------------------------------------
    function pollStatus() {
      fetch(`/cameras/${cameraId}/status`, {
        headers: { 'Accept': 'application/json' }
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (data && typeof data.is_recording === 'boolean') {
            setRecordingUI(data.is_recording);
          }
        })
        .catch(function () {});
    }

    pollStatus();
    const pollInterval = setInterval(pollStatus, 4000);
    window.addEventListener('beforeunload', function () {
      clearInterval(pollInterval);
    });
  });
})();
