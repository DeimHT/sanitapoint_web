const api = {
  async get(path) {
    const r = await fetch(path);
    api._checkAuth(r);
    if (!r.ok) throw await api._err(r);
    return r.json();
  },
  async post(path, body, { timeoutMs = 60000 } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const r = await fetch(path, {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      api._checkAuth(r);
      if (!r.ok) throw await api._err(r);
      return await r.json();
    } catch (e) {
      if (controller.signal.aborted) {
        const error = new Error("El servidor no respondió a tiempo. La operación puede haberse registrado; comprueba su estado antes de repetirla.");
        error.resultadoIncierto = true;
        throw error;
      }
      throw e;
    } finally { clearTimeout(timer); }
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
      el.textContent = `${ahora} | CAJA ABIERTA — ${caja.operador} | Contadores: Baño ${caja.contador_bano}${caja.servicio === "Ba\u00f1o 2" ? "" : ` · Ducha ${caja.contador_ducha}`}`;
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
  equipo: ["config_equipo"],
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
  const servicio = document.getElementById("nav_servicio");
  if (servicio) {
    servicio.hidden = !cuentaActual.servicio;
    servicio.textContent = cuentaActual.servicio || "";
    servicio.setAttribute("aria-label", `Servicio seleccionado: ${cuentaActual.servicio || ""}`);
  }
  if (nav) {
    const rolLabel = ETIQUETA_ROL[cuentaActual.rol] || cuentaActual.rol;
    nav.textContent = `${cuentaActual.nombre || cuentaActual.username} · ${rolLabel}`;
  }
  // Compatibilidad con paginas servidas durante una recarga del proceso:
  // si aun no tienen el contexto del menu, aplicar los permisos de la sesion.
  document.querySelectorAll("header.topnav a[data-nav]").forEach((a) => {
    if (cuentaActual.rol === "cajero") {
      a.hidden = !["venta", "caja"].includes(a.dataset.nav);
    } else {
      const caps = NAV_CAPS[a.dataset.nav] || [];
      a.hidden = !caps.some(c => puede(c)) && a.dataset.nav !== "equipo";
    }
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
