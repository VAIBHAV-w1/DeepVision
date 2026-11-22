/**
 * DeepVision CSRF Handling
 * Reads deepvision_django_csrftoken or csrftoken cookie, with API fallback.
 */

export function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

let cachedCsrfToken = '';
let inflightCsrfPromise = null;

export function setCsrfToken(token) {
  if (typeof token === 'string') {
    cachedCsrfToken = token;
  }
}

export function getCsrfToken() {
  return (
    getCookie('deepvision_django_csrftoken') ||
    getCookie('csrftoken') ||
    cachedCsrfToken ||
    ''
  );
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

export async function fetchCsrfToken() {
  if (inflightCsrfPromise) {
    return inflightCsrfPromise;
  }
  inflightCsrfPromise = (async () => {
    const delays = [0, 800, 1600, 3200];
    try {
      for (let attempt = 0; attempt < delays.length; attempt++) {
        if (delays[attempt] > 0) {
          await new Promise((r) => setTimeout(r, delays[attempt]));
        }
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);
        try {
          const res = await fetch(`${API_BASE_URL}/api/auth/csrf/`, {
            credentials: 'include',
            signal: controller.signal,
          });
          if (res.ok) {
            const data = await res.json();
            if (data && data.csrfToken) {
              setCsrfToken(data.csrfToken);
              return data.csrfToken;
            }
            return getCsrfToken();
          }
          if (![502, 503, 504].includes(res.status)) {
            break;
          }
        } catch (e) {
          if (attempt === delays.length - 1) {
            console.warn('Failed to fetch CSRF token:', e);
          }
        } finally {
          clearTimeout(timeoutId);
        }
      }
    } finally {
      inflightCsrfPromise = null;
    }
    return getCsrfToken();
  })();
  return inflightCsrfPromise;
}
