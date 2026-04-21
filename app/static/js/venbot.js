/**
 * venbot.js — JS global compartido por todas las páginas del dashboard.
 * Maneja: auth headers, refresh automático de token, helpers de API.
 */

const AUTH = {
  getAccessToken: () => localStorage.getItem('access_token'),
  getRefreshToken: () => localStorage.getItem('refresh_token'),
  setTokens: (access, refresh) => {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
  },
  clear: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },
  isAuthenticated: () => !!localStorage.getItem('access_token'),
};

/** Hace fetch autenticado. Si el token expiró, intenta refrescarlo. */
async function apiFetch(url, options = {}) {
  const token = AUTH.getAccessToken();
  if (!token) {
    window.location.href = '/auth/iniciar-sesion';
    return;
  }

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    ...(options.headers || {}),
  };

  let resp = await fetch(url, { ...options, headers });

  if (resp.status === 401) {
    // Intentar refrescar el token
    const refreshed = await _refreshToken();
    if (!refreshed) {
      AUTH.clear();
      window.location.href = '/auth/iniciar-sesion';
      return;
    }
    headers['Authorization'] = `Bearer ${AUTH.getAccessToken()}`;
    resp = await fetch(url, { ...options, headers });
  }

  return resp;
}

async function _refreshToken() {
  const refreshToken = AUTH.getRefreshToken();
  if (!refreshToken) return false;
  try {
    const resp = await fetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    AUTH.setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

/** Redirige al login si no hay token. Llamar al inicio de cada página protegida. */
function requireAuth() {
  if (!AUTH.isAuthenticated()) {
    window.location.href = '/auth/iniciar-sesion';
  }
}

/** Formatea un número como moneda (COP por defecto). */
function formatCurrency(amount, currency = 'COP') {
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
  }).format(amount);
}

/** Formatea una fecha ISO a formato legible en español. */
function formatDate(isoString) {
  if (!isoString) return '—';
  return new Intl.DateTimeFormat('es-CO', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(isoString));
}

/** Toast de notificación temporal. */
function toast(mensaje, tipo = 'info') {
  const colores = {
    info: 'bg-blue-900 border-blue-700 text-blue-200',
    success: 'bg-green-900 border-green-700 text-green-200',
    error: 'bg-red-900 border-red-700 text-red-200',
    warning: 'bg-yellow-900 border-yellow-700 text-yellow-200',
  };
  const div = document.createElement('div');
  div.className = `fixed bottom-4 right-4 z-50 px-4 py-3 rounded-xl border text-sm font-medium shadow-lg transition-all ${colores[tipo] || colores.info}`;
  div.textContent = mensaje;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}
