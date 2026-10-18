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

export function getCsrfToken() {
  return (
    getCookie('deepvision_django_csrftoken') ||
    getCookie('csrftoken') ||
    ''
  );
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

export async function fetchCsrfToken() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/csrf/`, { credentials: 'include' });
    if (res.ok) {
      const data = await res.json();
      return data.csrfToken || getCsrfToken();
    }
  } catch (e) {
    console.warn('Failed to fetch CSRF token:', e);
  }
  return getCsrfToken();
}
