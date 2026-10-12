/**
 * DeepVision Centralized API Client (api.js)
 * All frontend HTTP/JSON requests must route through this client.
 */

import { getCsrfToken, fetchCsrfToken } from '../utils/csrf';

async function request(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : endpoint;
  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {}),
  };

  const method = (options.method || 'GET').toUpperCase();

  // If sending JSON body, set Content-Type
  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  // Include CSRF Token for mutating methods
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    let csrfToken = getCsrfToken();
    if (!csrfToken) {
      csrfToken = await fetchCsrfToken();
    }
    if (csrfToken) {
      headers['X-CSRFToken'] = csrfToken;
    }
  }

  const response = await fetch(url, {
    ...options,
    method,
    headers,
    credentials: 'include',
  });

  // Handle unauthenticated response
  if (response.status === 401 && !url.includes('/api/auth/me')) {
    // Session expired or login required
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }

  // Parse JSON response
  let data = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (e) {
      data = null;
    }
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMsg = (data && typeof data === 'object' && (data.error || data.message))
      || `Request failed with status ${response.status}`;
    const error = new Error(errorMsg);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export const api = {
  // Authentication
  auth: {
    me: () => request('/api/auth/me/'),
    csrf: () => request('/api/auth/csrf/'),
    login: (email, password) => request('/api/auth/login/', { method: 'POST', body: { email, password } }),
    signup: (data) => request('/api/auth/signup/', { method: 'POST', body: data }),
    verifyOtp: (email, otp) => request('/api/auth/verify-otp/', { method: 'POST', body: { email, otp } }),
    resendOtp: (email) => request('/api/auth/resend-otp/', { method: 'POST', body: { email } }),
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
    getStats: (id) => request(`/cameras/${id}/stats/`),
    getStatus: (id) => request(`/cameras/${id}/status`),
    startRecording: (id) => request(`/cameras/${id}/record/start/`, { method: 'POST' }),
    stopRecording: (id) => request(`/cameras/${id}/record/stop/`, { method: 'POST' }),
    testCamera: (id) => request(`/api/cameras/${id}/test/`, { method: 'POST' }),
    testConnection: (sourceType, source) =>
      request('/api/cameras/test-connection/', { method: 'POST', body: { source_type: sourceType, source } }),
    warm: (id) => request(`/cameras/${id}/warm/`),
    getStreamUrl: (id, mode = 'tracking') => `/cameras/${id}/stream/?mode=${mode}`,
    getOriginalStreamUrl: (id) => `/cameras/${id}/stream/original/`,
    getTrackingStreamUrl: (id) => `/cameras/${id}/stream/tracking/`,
    getSnapshotUrl: (id) => `/cameras/${id}/snapshot/`,
  },

  // Recordings
  recordings: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/recordings/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/recordings/${id}/`),
    getViewUrl: (id) => `/recordings/${id}/view/`,
    getDownloadUrl: (id) => `/recordings/${id}/download/`,
  },

  // Evidence
  evidence: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/evidence/${q ? '?' + q : ''}`);
    },
    get: (id) => request(`/api/evidence/${id}/`),
    getPreviewUrl: (id) => `/evidence/${id}/preview/`,
    getDownloadUrl: (id) => `/evidence/${id}/download/`,
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
    addNote: (id, note) => request(`/api/cases/${id}/note/`, { method: 'POST', body: { note } }),
  },

  // Notifications
  notifications: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/notifications/${q ? '?' + q : ''}`);
    },
    unreadCount: () => request('/api/notifications/unread-count/'),
    markRead: (id) => request(`/notifications/${id}/read/`, { method: 'POST' }),
    markAllRead: () => request('/notifications/read-all/', { method: 'POST' }),
  },

  // DeepVision Assistant
  assistant: {
    chat: (message) => request('/api/assistant/chat/', { method: 'POST', body: { message } }),
  },

  // System Diagnostics
  health: {
    get: () => request('/api/health/'),
    getSurveillance: () => request('/api/surveillance/health/'),
  },
};

export default api;
