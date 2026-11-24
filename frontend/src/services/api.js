/**
 * DeepVision Centralized API Client (api.js)
 * All frontend HTTP/JSON requests must route through this client.
 */

import { getCsrfToken, fetchCsrfToken, setCsrfToken } from '../utils/csrf';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

const TRANSIENT_GATEWAY_STATUSES = new Set([502, 503, 504]);
const inFlightMutations = new Map();
const inFlightReads = new Map();
let isBackendUnavailable = false;

function parseRetryAfterSeconds(response) {
  const raw = response?.headers?.get?.('Retry-After');
  if (!raw) return 0;
  const asSec = Number(raw);
  if (Number.isFinite(asSec) && asSec > 0) {
    return Math.min(120, Math.max(1, Math.ceil(asSec)));
  }
  const asDate = Date.parse(raw);
  if (Number.isFinite(asDate)) {
    const delta = Math.ceil((asDate - Date.now()) / 1000);
    if (delta > 0) {
      return Math.min(120, Math.max(1, delta));
    }
  }
  return 0;
}

function isRenderHibernateResponse(response, parsedData = null) {
  if (!response || response.status !== 429) return false;
  const renderRouting = (response.headers?.get?.('X-Render-Routing') || '').toLowerCase();
  if (renderRouting.includes('hibernate') || renderRouting.includes('rate-limit')) {
    return true;
  }
  // Render cold-start 429 responds with plain-text "Too Many Requests" and never emits Django JSON rate-limit fields
  if (
    parsedData !== null &&
    typeof parsedData !== 'object'
  ) {
    return true;
  }
  if (
    parsedData &&
    typeof parsedData === 'object' &&
    !parsedData.scope &&
    !parsedData.retry_after &&
    !parsedData.cooldown &&
    !parsedData.code
  ) {
    return true;
  }
  return false;
}

function emitBackendStatus(detail) {
  if (detail && detail.available === false) {
    isBackendUnavailable = true;
  } else if (detail && detail.available === true) {
    if (!isBackendUnavailable) {
      return;
    }
    isBackendUnavailable = false;
  }
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    window.dispatchEvent(new CustomEvent('backend:status', { detail }));
  }
}

async function request(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  const timeoutMs = options.timeout || 25000;
  const method = (options.method || 'GET').toUpperCase();
  const isIdempotentRead = method === 'GET' || method === 'HEAD';
  const maxRetries = typeof options.maxRetries === 'number'
    ? options.maxRetries
    : (isIdempotentRead ? 4 : 0);

  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {}),
  };

  let bodyToSend = options.body;
  const isBinaryOrFormBody = (
    (typeof FormData !== 'undefined' && bodyToSend instanceof FormData) ||
    (typeof Blob !== 'undefined' && bodyToSend instanceof Blob) ||
    (typeof ArrayBuffer !== 'undefined' && bodyToSend instanceof ArrayBuffer) ||
    (typeof ArrayBuffer !== 'undefined' && ArrayBuffer.isView(bodyToSend))
  );
  // If sending plain JS object body, serialize as JSON and set Content-Type
  if (bodyToSend && typeof bodyToSend === 'object' && !isBinaryOrFormBody) {
    headers['Content-Type'] = 'application/json';
    bodyToSend = JSON.stringify(bodyToSend);
  }

  // Prevent duplicate concurrent non-idempotent mutations (excluding high-frequency ingest frames and FormData uploads)
  const isMutation = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
  const skipDedup = endpoint.includes('/ingest-frame') || bodyToSend instanceof FormData;
  const dedupKey = (isMutation && !skipDedup)
    ? `${method}:${url}:${typeof bodyToSend === 'string' ? bodyToSend : ''}`
    : null;
  const readDedupKey = (isIdempotentRead && !options.signal && !options.skipDedup)
    ? `${method}:${url}`
    : null;

  if (dedupKey && inFlightMutations.has(dedupKey)) {
    return inFlightMutations.get(dedupKey);
  }
  if (readDedupKey && inFlightReads.has(readDedupKey)) {
    return inFlightReads.get(readDedupKey);
  }

  const executeAttempt = async () => {
    // Include CSRF Token for mutating methods BEFORE starting the request timeout timer
    if (isMutation) {
      let csrfToken = getCsrfToken();
      if (!csrfToken) {
        csrfToken = await fetchCsrfToken();
      }
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }
    }

    let hibernatePostRetries = 0;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      if (attempt > 0) {
        const backoffMs = Math.min(8000, 1200 * (2 ** (attempt - 1)));
        emitBackendStatus({
          available: false,
          waking: true,
          retrying: true,
          attempt,
          maxRetries,
          message: `Backend server is waking up or temporarily unreachable. Retrying automatically (${attempt}/${maxRetries})...`,
        });
        await new Promise((r) => setTimeout(r, backoffMs));
      }

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
      let onCallerAbort = null;
      if (options.signal) {
        if (options.signal.aborted) {
          clearTimeout(timeoutId);
          throw new DOMException('Aborted', 'AbortError');
        }
        onCallerAbort = () => controller.abort();
        options.signal.addEventListener('abort', onCallerAbort, { once: true });
      }

      try {
        const fetchOptions = {
          ...options,
          body: bodyToSend,
          signal: controller.signal,
          method,
          headers,
          credentials: 'include',
        };
        delete fetchOptions.timeout;
        delete fetchOptions.maxRetries;
        delete fetchOptions.skipDedup;

        const response = await fetch(url, fetchOptions);
        clearTimeout(timeoutId);

        if (isIdempotentRead && TRANSIENT_GATEWAY_STATUSES.has(response.status) && attempt < maxRetries) {
          continue;
        }

        // Parse JSON or text payload before handling 429/error formatting
        let data = null;
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          try {
            data = await response.json();
            if (data && typeof data === 'object' && data.csrfToken) {
              setCsrfToken(data.csrfToken);
            }
          } catch (e) {
            data = null;
          }
        } else {
          data = await response.text();
        }

        const isHibernate429 = isRenderHibernateResponse(response, data);
        const retryAfterSec = parseRetryAfterSeconds(response) || Number(data?.retry_after || data?.cooldown || 0);

        if (response.status === 429 && isHibernate429) {
          const waitMs = Math.min(8000, Math.max(2500, (retryAfterSec || 3) * 1000));
          if (isIdempotentRead && attempt < maxRetries) {
            emitBackendStatus({
              available: false,
              waking: true,
              retrying: true,
              status: 429,
              message: 'Backend server is waking from idle hibernation (rate limit cooldown). Retrying automatically...',
            });
            await new Promise((r) => setTimeout(r, waitMs));
            continue;
          }
          if (isMutation && !skipDedup && hibernatePostRetries < 1) {
            hibernatePostRetries += 1;
            emitBackendStatus({
              available: false,
              waking: true,
              retrying: true,
              status: 429,
              message: 'Backend server is waking from idle hibernation. Completing sign-in...',
            });
            await new Promise((r) => setTimeout(r, waitMs));
            attempt -= 1;
            continue;
          }
        }

        // Backend answered cleanly if not a gateway/hibernate availability failure
        if (!TRANSIENT_GATEWAY_STATUSES.has(response.status) && !isHibernate429) {
          emitBackendStatus({ available: true, waking: false, retrying: false, status: response.status });
        }

        // Handle unauthenticated response
        if (response.status === 401 && !url.includes('/api/auth/me')) {
          window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }

        // Special clean handling for auth/me unauthenticated state
        if (response.status === 401 && url.includes('/api/auth/me')) {
          return { authenticated: false, user: null };
        }

        if (!response.ok) {
          let errorMsg;
          if (data && typeof data === 'object' && (data.error || data.message || data.detail)) {
            errorMsg = data.error || data.message || data.detail;
          } else if (response.status === 429) {
            if (isHibernate429) {
              errorMsg = 'Backend server is waking up from idle hibernation (hosting proxy rate limit). Please wait a few seconds and try again.';
              emitBackendStatus({ available: false, waking: true, retrying: false, status: 429, message: errorMsg });
            } else {
              errorMsg = retryAfterSec
                ? `Too many requests. Please wait ${retryAfterSec} seconds before trying again.`
                : 'Too many requests. Please wait a few seconds before trying again.';
            }
          } else if (response.status === 502 || response.status === 504) {
            errorMsg = 'Backend server is waking up or temporarily unreachable (HTTP ' + response.status + '). Please retry in a few seconds.';
            emitBackendStatus({ available: false, waking: true, retrying: false, status: response.status, message: errorMsg });
          } else if (response.status === 503) {
            errorMsg = 'Database or service temporarily unavailable. Please retry in a few moments.';
            emitBackendStatus({ available: false, waking: true, retrying: false, status: 503, message: errorMsg });
          } else if (response.status === 403 && typeof data === 'string' && data.includes('CSRF')) {
            setCsrfToken('');
            errorMsg = 'Security validation failed (CSRF token expired). Please refresh the page.';
          } else if (response.status === 401) {
            errorMsg = 'Authentication required. Please sign in to proceed.';
          } else {
            errorMsg = `Request failed (${response.status}). Please try again later.`;
          }
          const error = new Error(errorMsg);
          error.status = response.status;
          error.data = data;
          if (response.status === 429) {
            error.retryAfter = retryAfterSec || (isHibernate429 ? 5 : 15);
            error.isHibernateRateLimited = isHibernate429;
          }
          error.isTransientUnavailable = TRANSIENT_GATEWAY_STATUSES.has(response.status) || isHibernate429;
          throw error;
        }

        return data;
      } catch (err) {
        clearTimeout(timeoutId);
        const callerAborted = Boolean(options.signal && options.signal.aborted);
        const isTransientNetError = !callerAborted && (err.name === 'AbortError' || err.name === 'TypeError');
        if (isIdempotentRead && isTransientNetError && attempt < maxRetries) {
          continue;
        }
        if (err.name === 'AbortError') {
          const timeoutErr = new Error(`Request timed out after ${timeoutMs}ms: ${endpoint}`);
          timeoutErr.name = 'TimeoutError';
          timeoutErr.status = 408;
          timeoutErr.isTransientUnavailable = !callerAborted;
          if (!callerAborted) {
            emitBackendStatus({ available: false, waking: true, retrying: false, status: 408, message: 'Backend server is taking longer than expected to respond.' });
          }
          throw timeoutErr;
        }
        if (err.name === 'TypeError') {
          emitBackendStatus({ available: false, waking: true, retrying: false, status: 0, message: 'Unable to reach backend server. Retrying connection...' });
        }
        throw err;
      } finally {
        clearTimeout(timeoutId);
        if (options.signal && onCallerAbort) {
          options.signal.removeEventListener('abort', onCallerAbort);
        }
      }
    }
  };

  const promise = executeAttempt();
  if (dedupKey) {
    inFlightMutations.set(dedupKey, promise);
    promise.finally(() => {
      if (inFlightMutations.get(dedupKey) === promise) {
        inFlightMutations.delete(dedupKey);
      }
    });
  } else if (readDedupKey) {
    inFlightReads.set(readDedupKey, promise);
    promise.finally(() => {
      if (inFlightReads.get(readDedupKey) === promise) {
        inFlightReads.delete(readDedupKey);
      }
    });
  }
  return promise;
}

export const api = {
  system: {
    health: (options = {}) => request('/api/health/', { timeout: 12000, maxRetries: 2, ...options }),
    live: (options = {}) => request('/api/health/live/', { timeout: 8000, maxRetries: 1, ...options }),
  },

  // Authentication
  auth: {
    me: (options = {}) => request('/api/auth/me/', { timeout: 22000, maxRetries: 2, ...options }),
    csrf: () => request('/api/auth/csrf/'),
    login: (email, password) => request('/api/auth/login/', { method: 'POST', body: { email, password } }),
    verifyLoginOtp: (email, otp) => request('/api/auth/verify-login-otp/', { method: 'POST', body: { email, otp } }),
    resendLoginOtp: (email) => request('/api/auth/resend-login-otp/', { method: 'POST', body: { email } }),
    signup: (data) => request('/api/auth/signup/', { method: 'POST', body: data }),
    verifyOtp: (email, otp) => request('/api/auth/verify-otp/', { method: 'POST', body: { email, otp, purpose: 'signup' } }),
    resendOtp: (email) => request('/api/auth/resend-otp/', { method: 'POST', body: { email, purpose: 'signup' } }),
    forgotPassword: (email) => request('/api/auth/forgot-password/', { method: 'POST', body: { email } }),
    verifyResetOtp: (email, otp) => request('/api/auth/verify-reset-otp/', { method: 'POST', body: { email, otp } }),
    resetPassword: (emailOrData, otp, newPassword, confirmPassword) => {
      let payload;
      if (typeof emailOrData === 'object' && emailOrData !== null) {
        payload = {
          email: emailOrData.email,
          otp: emailOrData.otp || emailOrData.reset_code || emailOrData.code,
          new_password: emailOrData.new_password || emailOrData.newPassword,
          confirm_password: emailOrData.confirm_password || emailOrData.confirmPassword,
        };
      } else {
        payload = {
          email: emailOrData,
          otp: otp,
          new_password: newPassword,
          confirm_password: confirmPassword,
        };
      }
      return request('/api/auth/reset-password/', { method: 'POST', body: payload });
    },
    logout: () => request('/api/auth/logout/', { method: 'POST' }),
  },

  // Dashboard
  dashboard: {
    getStats: () => request('/api/dashboard/stats/'),
  },

  // Cameras
  cameras: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/cameras/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/cameras/${id}/`),
    create: (data) => request('/api/cameras/', { method: 'POST', body: data }),
    update: (id, data) => request(`/api/cameras/${id}/`, { method: 'PUT', body: data }),
    remove: (id) => request(`/api/cameras/${id}/`, { method: 'DELETE' }),
    getStats: (id) => request(`/api/cameras/${id}/stats/`),
    getStatus: (id) => request(`/api/cameras/${id}/status/`),
    startRecording: (id) => request(`/api/cameras/${id}/record/start/`, { method: 'POST' }),
    stopRecording: (id) => request(`/api/cameras/${id}/record/stop/`, { method: 'POST' }),
    testCamera: (id) => request(`/api/cameras/${id}/test/`, { method: 'POST' }),
    testConnection: (sourceType, source, username = '', password = '') =>
      request('/api/cameras/test-connection/', {
        method: 'POST',
        body: { source_type: sourceType, source, username, password },
      }),
    ingestFrame: (id, framePayload, seq = null) => {
      const q = seq !== null ? `?seq=${encodeURIComponent(seq)}` : '';
      if (typeof Blob !== 'undefined' && framePayload instanceof Blob) {
        return request(`/api/cameras/${id}/ingest-frame/${q}`, {
          method: 'POST',
          headers: { 'Content-Type': framePayload.type || 'image/jpeg' },
          body: framePayload,
          timeout: 12000,
        });
      }
      return request(`/api/cameras/${id}/ingest-frame/${q}`, {
        method: 'POST',
        body: { frame: framePayload },
        timeout: 12000,
      });
    },
    disconnect: (id) => request(`/api/cameras/${id}/disconnect/`, { method: 'POST' }),
    warm: (id, captureOnly = false) =>
      request(`/api/cameras/${id}/warm/${captureOnly ? '?capture_only=1' : ''}`, { method: 'POST' }),
    getStreamUrl: (id, mode = 'tracking') => `${API_BASE_URL}/api/cameras/${id}/stream/?mode=${mode}`,
    getOriginalStreamUrl: (id) => `${API_BASE_URL}/api/cameras/${id}/stream/original/`,
    getTrackingStreamUrl: (id) => `${API_BASE_URL}/api/cameras/${id}/stream/tracking/`,
    getSnapshotUrl: (id) => `${API_BASE_URL}/api/cameras/${id}/snapshot/`,
    captureSnapshot: (id) => request(`/api/cameras/${id}/snapshot/`, { method: 'POST' }),
    snapshot: (id) => request(`/api/cameras/${id}/snapshot/`, { method: 'POST' }),
    // Detection Rules, Presets & Security Zones
    getRules: (id) => request(`/api/cameras/${id}/rules/`),
    saveRules: (id, data) => request(`/api/cameras/${id}/rules/`, { method: 'POST', body: data }),
    getScene: (id) => request(`/api/cameras/${id}/scene/`),
    analyzeScene: (id) => request(`/api/cameras/${id}/scene/`, { method: 'POST' }),
    applyPreset: (id, presetKey) => request(`/api/cameras/${id}/rules/preset/`, { method: 'POST', body: { preset: presetKey } }),
    getPresets: () => request('/api/presets/'),
    getZones: (id) => request(`/api/cameras/${id}/zones/`),
    createZone: (id, zoneData) => request(`/api/cameras/${id}/zones/`, { method: 'POST', body: zoneData }),
    deleteZone: (camId, zoneId) => request(`/api/cameras/${camId}/zones/${zoneId}/delete/`, { method: 'POST' }),
    toggleZone: (camId, zoneId) => request(`/api/cameras/${camId}/zones/${zoneId}/toggle/`, { method: 'POST' }),
  },

  // Recordings
  recordings: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/recordings/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/recordings/${id}/`),
    remove: (id) => request(`/api/recordings/${id}/`, { method: 'DELETE' }),
    retryUpload: (id) => request(`/api/recordings/${id}/retry-upload/`, { method: 'POST' }),
    getViewUrl: (id) => `${API_BASE_URL}/recordings/${id}/view/`,
    getDownloadUrl: (id) => `${API_BASE_URL}/recordings/${id}/download/`,
  },

  // Evidence
  evidence: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/evidence/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/evidence/${id}/`),
    remove: (id) => request(`/api/evidence/${id}/`, { method: 'DELETE' }),
    getPreviewUrl: (id) => `${API_BASE_URL}/evidence/${id}/preview/`,
    getDownloadUrl: (id) => `${API_BASE_URL}/evidence/${id}/download/`,
  },

  // Alerts & Incident Workspace
  alerts: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/alerts/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/alerts/${id}/`),
    getIncidentContext: (id) => request(`/api/alerts/${id}/incident-context/`),
    getScopedEvidence: (id) => request(`/api/alerts/${id}/evidence/`),
    getScopedRecordings: (id) => request(`/api/alerts/${id}/recordings/`),
    getScopedCase: (id) => request(`/api/alerts/${id}/case/`),
    getScopedNotifications: (id) => request(`/api/alerts/${id}/notifications/`),
    getScopedTimeline: (id) => request(`/api/alerts/${id}/timeline/`),
    acknowledge: (id) => request(`/alerts/${id}/acknowledge/`, { method: 'POST' }),
    resolve: (id) => request(`/alerts/${id}/resolve/`, { method: 'POST' }),
    analyze: (id) => request(`/api/alerts/${id}/analyze/`, { method: 'POST' }),
    bulkAction: (action, alertIds) => request('/api/alerts/bulk-action/', { method: 'POST', body: { action, alert_ids: alertIds } }),
    createCase: (id, data = {}) => request(`/api/alerts/${id}/create-case/`, { method: 'POST', body: data }),
    addNote: (id, note) => request(`/api/alerts/${id}/note/`, { method: 'POST', body: { note } }),
  },

  // Incident Cases
  cases: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/cases/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/cases/${id}/`),
    update: (id, data) => request(`/api/cases/${id}/`, { method: 'PATCH', body: data }),
    addNote: (id, note) => request(`/api/cases/${id}/note/`, { method: 'POST', body: { note } }),
  },

  // SOC Policies & Playbooks
  soc: {
    getPolicies: () => request('/api/soc/policies/'),
    createPolicy: (data) => request('/api/soc/policies/', { method: 'POST', body: data }),
    updatePolicy: (id, data) => request(`/api/soc/policies/${id}/`, { method: 'PATCH', body: data }),
    deletePolicy: (id) => request(`/api/soc/policies/${id}/`, { method: 'DELETE' }),
    getPlaybooks: () => request('/api/soc/playbooks/'),
    createPlaybook: (data) => request('/api/soc/playbooks/', { method: 'POST', body: data }),
    updatePlaybook: (id, data) => request(`/api/soc/playbooks/${id}/`, { method: 'PATCH', body: data }),
    deletePlaybook: (id) => request(`/api/soc/playbooks/${id}/`, { method: 'DELETE' }),
  },

  // Notifications
  notifications: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/notifications/${q ? '?' + q : ''}`);
    },
    unreadCount: () => request('/api/notifications/unread-count/'),
    getPreferences: () => request('/api/notifications/preferences/'),
    savePreferences: (data) => request('/api/notifications/preferences/', { method: 'POST', body: data }),
    getDeliveryStatus: (limit = 30) => request(`/api/notifications/delivery-status/?limit=${limit}`),
    sendTestEmail: (recipient = '') => request('/api/notifications/test-email/', { method: 'POST', body: recipient ? { recipient } : {} }),
    markRead: (id) => request(`/notifications/${id}/read/`, { method: 'POST' }),
    markAsRead: (id) => request(`/notifications/${id}/read/`, { method: 'POST' }),
    markAllRead: () => request('/notifications/read-all/', { method: 'POST' }),
    markAllAsRead: () => request('/notifications/read-all/', { method: 'POST' }),
  },

  // Detection & System Settings
  settings: {
    getDetection: () => request('/api/settings/detection/'),
    saveDetection: (data) => request('/api/settings/detection/', { method: 'POST', body: data }),
    getClip: () => request('/api/settings/clip/'),
    saveClip: (data) => request('/api/settings/clip/', { method: 'POST', body: data }),
  },
  clip: {
    getEvents: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/surveillance/clip/events/${q ? '?' + q : ''}`);
    },
  },

  // DeepVision Assistant
  assistant: {
    chat: (message) => request('/api/assistant/chat/', { method: 'POST', body: { message } }),
  },

  // System Diagnostics & Admin Uptime Monitoring
  health: {
    get: () => request('/api/health/'),
    getSurveillance: () => request('/api/surveillance/health/'),
  },
  uptime: {
    getStatus: () => request('/api/uptime/status/'),
    checkNow: () => request('/api/uptime/check-now/', { method: 'POST' }),
  },
};

export default api;
