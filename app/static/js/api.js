const api = {
  async get(path) {
    const r = await fetch(path);
    api._checkAuth(r);
    if (!r.ok) throw await api._err(r);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    api._checkAuth(r);
    if (!r.ok) throw await api._err(r);
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    api._checkAuth(r);
    if (!r.ok) throw await api._err(r);
    return r.json();
  },
  _checkAuth(r) {
    // Sesión expirada o no autenticado → volver al login.
    if (r.status === 401) {
      window.location = "/login";
      throw new Error("No autenticado");
    }
  },
  async _err(r) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    return new Error(detail);
  },
};

function fmtMonto(n) {
  return "$" + Number(n || 0).toLocaleString("es-CL");
}

async function refrescarStatusbar() {
  const el = document.getElementById("statusbar");
  if (!el) return;
  try {
    const caja = await api.get("/api/caja");
    const ahora = new Date().toLocaleString("es-CL");
    if (caja) {
      el.innerHTML = `${ahora} &nbsp;|&nbsp; <span class="pill abierta">CAJA ABIERTA</span> — ${caja.operador}`;
    } else {
      el.innerHTML = `${ahora} &nbsp;|&nbsp; <span class="pill cerrada">CAJA CERRADA</span>`;
    }
  } catch (e) {
    el.textContent = "Sin conexión con el servidor";
  }
}

let cuentaActual = null;

const ETIQUETA_ROL = {
  cajero: "Cajero", supervisor: "Supervisor",
  contabilidad: "Contabilidad", administrador: "Administrador",
};

// Enlace del nav -> capacidades que lo hacen visible (basta una).
const NAV_CAPS = {
  venta: ["emitir_boletas"],
  caja: ["caja_apertura", "caja_cierre", "caja_retiro"],
  historial: ["ver_historial"],
  cierres: ["ver_cierres"],
  clientes: ["gestionar_clientes"],
  reportes: ["ver_reportes"],
  config: ["configuracion"],
  cuentas: ["gestionar_cuentas"],
};

function puede(cap) {
  return !!(cuentaActual && cuentaActual.caps && cuentaActual.caps.includes(cap));
}

async function cargarUsuarioNav() {
  try {
    cuentaActual = await api.get("/api/auth/me");
  } catch (e) {
    return; // si 401, api._checkAuth ya redirige al login
  }
  const nav = document.getElementById("nav_user");
  if (nav) {
    const rolLabel = ETIQUETA_ROL[cuentaActual.rol] || cuentaActual.rol;
    nav.textContent = `${cuentaActual.nombre || cuentaActual.username} · ${rolLabel}`;
  }
  // Mostrar cada enlace del nav si el rol tiene alguna de sus capacidades.
  document.querySelectorAll("header.topnav a[data-nav]").forEach((a) => {
    const caps = NAV_CAPS[a.dataset.nav] || [];
    a.hidden = !caps.some((c) => puede(c));
  });
  const btn = document.getElementById("nav_logout");
  if (btn) {
    btn.hidden = false;
    btn.onclick = async () => {
      try { await api.post("/api/auth/logout"); } catch (e) {}
      window.location = "/login";
    };
  }
  document.dispatchEvent(new CustomEvent("cuenta-lista", { detail: cuentaActual }));
}

document.addEventListener("DOMContentLoaded", () => {
  cargarUsuarioNav();
  refrescarStatusbar();
  setInterval(refrescarStatusbar, 30000);

  const path = window.location.pathname;
  document.querySelectorAll("header.topnav a").forEach((a) => {
    if (a.getAttribute("href") === path) a.classList.add("active");
  });
});
