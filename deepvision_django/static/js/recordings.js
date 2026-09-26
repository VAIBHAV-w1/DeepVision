/**
 * DeepVision Smart Surveillance — Recordings Library Script
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const cameraFilter = document.getElementById('recordings-camera-filter');
    const searchInput = document.getElementById('recordings-search');
    const recordingCards = document.querySelectorAll('.recording-card, .recording-table-row');

    function filterRecordings() {
      const selectedCam = cameraFilter ? cameraFilter.value.trim().toLowerCase() : '';
      const query = searchInput ? searchInput.value.trim().toLowerCase() : '';

      recordingCards.forEach(function (el) {
        const cam = (el.getAttribute('data-camera-name') || '').toLowerCase();
        const text = el.textContent.toLowerCase();

        const matchesCam = !selectedCam || cam === selectedCam;
        const matchesQuery = !query || text.includes(query);

        if (matchesCam && matchesQuery) {
          el.style.display = '';
        } else {
          el.style.display = 'none';
        }
      });
    }

    if (cameraFilter) {
      cameraFilter.addEventListener('change', filterRecordings);
    }

    if (searchInput) {
      searchInput.addEventListener('input', filterRecordings);
    }
  });
})();
