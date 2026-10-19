(() => {
  const script = document.currentScript;
  const timeoutSeconds = Number(script?.dataset.timeout || 1800);
  const loginUrl = script?.dataset.login || "/login";
  const heartbeatUrl = script?.dataset.heartbeat || "/api/session/activity";
  const timeoutMs = timeoutSeconds * 1000;
  const warningSeconds = Math.min(60, Math.max(1, timeoutSeconds - 1));
  const heartbeatGapMs = 60 * 1000;
  let lastHeartbeat = 0;
  let expirationTimer;
  let warningTimer;
  let countdownTimer;
  let lastLocalActivity = 0;

  const warning = document.createElement("div");
  warning.hidden = true;
  warning.setAttribute("role", "dialog");
  warning.setAttribute("aria-modal", "true");
  warning.setAttribute("aria-labelledby", "idle-warning-title");
  warning.innerHTML = `<div class="idle-warning-card"><div class="idle-warning-icon">!</div><div><strong id="idle-warning-title">Tu sesión está por expirar</strong><p>Tu sesión expirará en <b id="idle-countdown">${warningSeconds}</b> segundos por inactividad. ¿Deseas continuar conectado?</p><button type="button" id="idle-continue">Continuar conectado</button></div></div>`;
  const style = document.createElement("style");
  style.textContent = `.idle-warning-overlay{position:fixed;inset:0;z-index:99999;display:grid;place-items:center;padding:20px;background:#102b48a8;backdrop-filter:blur(4px)}.idle-warning-overlay[hidden]{display:none}.idle-warning-card{display:grid;grid-template-columns:48px 1fr;gap:15px;width:min(510px,94vw);padding:22px;border:1px solid #c9dced;border-radius:20px;background:#fff;color:#17324d;box-shadow:0 25px 70px #071a2e66;font-family:Inter,Segoe UI,Arial,sans-serif}.idle-warning-icon{display:grid;place-items:center;width:48px;height:48px;border-radius:50%;background:#fff3d6;color:#9a6500;font-size:27px;font-weight:900}.idle-warning-card strong{font-size:20px}.idle-warning-card p{margin:8px 0 17px;line-height:1.5;color:#526b83}.idle-warning-card button{border:0;border-radius:11px;padding:11px 16px;background:linear-gradient(135deg,#2d77ff,#14b8a6);color:#fff;font-weight:800;cursor:pointer}`;
  warning.className = "idle-warning-overlay";
  document.head.appendChild(style);
  document.body.appendChild(warning);

  function hideWarning() {
    warning.hidden = true;
    clearInterval(countdownTimer);
  }

  function showWarning() {
    let remaining = warningSeconds;
    const counter = warning.querySelector("#idle-countdown");
    counter.textContent = remaining;
    warning.hidden = false;
    warning.querySelector("#idle-continue").focus();
    clearInterval(countdownTimer);
    countdownTimer = setInterval(() => {
      remaining -= 1;
      counter.textContent = Math.max(remaining, 0);
      if (remaining <= 0) clearInterval(countdownTimer);
    }, 1000);
  }

  function scheduleExpiration() {
    clearTimeout(expirationTimer);
    clearTimeout(warningTimer);
    hideWarning();
    warningTimer = setTimeout(showWarning, Math.max(0, timeoutMs - warningSeconds * 1000));
    expirationTimer = setTimeout(() => {
      window.location.assign(`${loginUrl}?expired=1`);
    }, timeoutMs + 1000);
  }

  async function registerActivity(force = false) {
    const now = Date.now();
    scheduleExpiration();
    if (window.parent !== window) window.parent.postMessage("pharma-user-activity", window.location.origin);
    if (!force && now - lastHeartbeat < heartbeatGapMs) return;
    lastHeartbeat = now;
    try {
      const response = await fetch(heartbeatUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", "X-User-Activity": "1" },
      });
      if (response.status === 401) window.location.assign(`${loginUrl}?expired=1`);
    } catch (_) {
      // Un fallo temporal de red no debe ampliar una sesión en el servidor.
    }
  }

  function handleActivity() {
    const now = Date.now();
    if (now - lastLocalActivity < 1000) return;
    lastLocalActivity = now;
    registerActivity(false);
  }

  ["mousemove", "pointerdown", "keydown", "touchstart", "scroll"].forEach((eventName) => {
    window.addEventListener(eventName, handleActivity, { passive: true });
  });
  warning.querySelector("#idle-continue").addEventListener("click", () => registerActivity(true));
  window.addEventListener("message", (event) => {
    if (event.origin === window.location.origin && event.data === "pharma-user-activity") registerActivity();
  });
  scheduleExpiration();
})();
