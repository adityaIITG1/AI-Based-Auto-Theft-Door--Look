// =======================
// ARGUS Frontend Connector
// Matches YOUR index.html IDs
// =======================

const WS_URL = "ws://127.0.0.1:8000/ws/stream";
const API_BASE = "http://127.0.0.1:8000";

// --- Elements ---
const statusPill = document.getElementById("statusPill");
const riskScoreText = document.getElementById("riskScoreText");
const riskFill = document.getElementById("riskFill");
const detectionList = document.getElementById("detectionList");
const remoteStatus = document.getElementById("remoteStatus");

const lockBtn = document.getElementById("lockBtn");
const unlockBtn = document.getElementById("unlockBtn");
const sirenBtn = document.getElementById("sirenBtn");

const notifyBtn = document.getElementById("notifyBtn");
const policeBtn = document.getElementById("policeBtn");
const clipBtn = document.getElementById("clipBtn");

// --- Helpers ---
function setPill(state) {
  // expects: safe / warning / critical
  statusPill.classList.remove("safe", "warning", "critical");
  statusPill.classList.add(state);

  if (state === "critical") statusPill.textContent = "CRITICAL";
  else if (state === "warning") statusPill.textContent = "WARNING";
  else statusPill.textContent = "SAFE";
}

function setRiskUI(score) {
  // Score is 0-100
  const clamped = Math.max(0, Math.min(100, Number(score || 0)));
  riskFill.style.width = clamped + "%";

  if (clamped >= 80) {
    riskScoreText.textContent = "CRITICAL";
    setPill("critical");
  } else if (clamped >= 50) {
    riskScoreText.textContent = "WARNING";
    setPill("warning");
  } else {
    riskScoreText.textContent = "LOW";
    setPill("safe");
  }
}

function addDetectionLine(text, type = "muted") {
  // type: muted / warn / danger
  const li = document.createElement("li");
  li.className = type;
  li.textContent = text;
  detectionList.prepend(li);

  // keep only 10 lines
  while (detectionList.children.length > 10) {
    detectionList.removeChild(detectionList.lastChild);
  }
  return li;
}

function clearMutedIfNeeded() {
  const first = detectionList.querySelector(".muted");
  if (first) first.remove();
}

function fmtPct(x) {
  return Math.round((Number(x || 0) * 100)) + "%";
}

function setRemoteStatus(text, boldText = "") {
  remoteStatus.innerHTML = `Remote Status: <b>${boldText || text}</b>${boldText ? " " + text : ""}`;
}

// --- Actuator API calls ---
async function post(path) {
  const res = await fetch(API_BASE + path, { method: "POST" });
  return await res.json();
}

lockBtn?.addEventListener("click", async () => {
  try {
    setRemoteStatus("Locking...", "Working");
    await post("/api/actuators/lock");
    setRemoteStatus("Gate locked.", "LOCKED");
    clearMutedIfNeeded();
    addDetectionLine("🔒 Gate locked manually by operator", "warn");
  } catch {
    setRemoteStatus("Lock failed (backend not reachable).", "ERROR");
  }
});

unlockBtn?.addEventListener("click", async () => {
  try {
    setRemoteStatus("Unlocking...", "Working");
    await post("/api/actuators/unlock");
    setRemoteStatus("Gate unlocked.", "UNLOCKED");
    clearMutedIfNeeded();
    addDetectionLine("🔓 Gate unlocked manually by operator", "muted");
  } catch {
    setRemoteStatus("Unlock failed (backend not reachable).", "ERROR");
  }
});

sirenBtn?.addEventListener("click", async () => {
  try {
    setRemoteStatus("Activating siren...", "Working");
    await post("/api/actuators/siren");
    setRemoteStatus("Siren ON.", "SIREN ON");
    clearMutedIfNeeded();
    addDetectionLine("🚨 Siren activated manually by operator", "danger");
  } catch {
    setRemoteStatus("Siren failed (backend not reachable).", "ERROR");
  }
});

// --- Demo buttons ---
notifyBtn?.addEventListener("click", () => alert("Guard notified (demo)."));
policeBtn?.addEventListener("click", () => alert("Police notified (demo)."));
clipBtn?.addEventListener("click", () => alert("30s clip saved (demo)."));

// --- Setup EmailJS ---
// PLACEHOLDER: Replace with your actual Public Key
emailjs.init("YOUR_PUBLIC_KEY");

const SERVICE_ID = "YOUR_SERVICE_ID";
const TEMPLATE_ID = "YOUR_TEMPLATE_ID";

// --- Rate Limit Emails ---
let lastEmailTime = 0;
const EMAIL_COOLDOWN = 120000; // 2 minutes

function sendEmailAlert(type, risk) {
  const now = Date.now();
  if (now - lastEmailTime < EMAIL_COOLDOWN) return;

  emailjs.send(SERVICE_ID, TEMPLATE_ID, {
    threat_type: type,
    risk_score: risk,
    message: `Critical Security Alert: ${type}. Immediate action required.`,
    timestamp: new Date().toLocaleString()
  }).then(() => {
    addDetectionLine("📧 Alert Email Sent to Admin", "info");
    console.log("Email sent successfully");
  }).catch((err) => {
    console.error("EmailJS Failed:", err);
    addDetectionLine("⚠️ Email Alert Failed (Check Config)", "muted");
  });

  lastEmailTime = now;
}

// --- Report Generation ---
const reportBtn = document.getElementById("reportBtn");
reportBtn?.addEventListener("click", () => {
  // Download directly from Backend
  window.location.href = API_BASE + "/api/report/generate";
});

// --- Role Switching ---
// --- Role Switching ---
const roleGuardBtn = document.getElementById("roleGuardBtn");
const roleAdminBtn = document.getElementById("roleAdminBtn");
const remoteCard = document.getElementById("remoteCard");
const roleText = document.getElementById("roleText");

function setGuardMode() {
  // remoteCard.style.display = "none";
  [lockBtn, unlockBtn, sirenBtn].forEach(btn => {
    if (btn) {
      btn.disabled = true;
      btn.style.opacity = "0.5";
      btn.style.cursor = "not-allowed";
    }
  });

  roleGuardBtn.classList.add("primary");
  roleAdminBtn.classList.remove("primary");
  roleText.textContent = "GUARD";
  // addDetectionLine("Switched to Guard View", "muted");
}

function setAdminMode() {
  // remoteCard.style.display = "block";
  [lockBtn, unlockBtn, sirenBtn].forEach(btn => {
    if (btn) {
      btn.disabled = false;
      btn.style.opacity = "1";
      btn.style.cursor = "pointer";
    }
  });

  roleAdminBtn.classList.add("primary");
  roleGuardBtn.classList.remove("primary");
  roleText.textContent = "ADMIN";
  // addDetectionLine("Switched to Admin View", "muted"); 
}

roleGuardBtn?.addEventListener("click", () => {
  setGuardMode();
  addDetectionLine("Switched to Guard View (Controls Disabled)", "muted");
});

roleAdminBtn?.addEventListener("click", () => {
  setAdminMode();
  addDetectionLine("Switched to Admin View (Controls Enabled)", "muted");
});

// Init Default State
setGuardMode();

// --- Incident Modal Logic ---
const incidentModal = document.getElementById("incidentModal");
const incidentDetails = document.getElementById("incidentDetails");
const closeModalBtn = document.getElementById("closeModalBtn");
const modalDownloadBtn = document.getElementById("modalDownloadBtn");
let isIncidentActive = false;

function showAutoReport(type, risk, ts) {
  if (isIncidentActive) return; // Already showing

  isIncidentActive = true;
  incidentModal.style.display = "flex";

  incidentDetails.innerHTML = `
        <div class="incident-row"><strong>Type:</strong> ${type.toUpperCase()}</div>
        <div class="incident-row"><strong>Risk Score:</strong> ${risk}/100</div>
        <div class="incident-row"><strong>Time:</strong> ${ts}</div>
        <div class="incident-row" style="color:#4caf50; font-size:1.0rem; margin-top:1rem;">
           ✅ <strong>Gate Locked</strong><br>
           ✅ <strong>Siren Activated</strong><br>
           ✅ <strong>Email Alert Sent</strong>
        </div>
    `;

  // Play sound? (Optional)
}

closeModalBtn?.addEventListener("click", () => {
  incidentModal.style.display = "none";
  // Cooldown before showing again? 
  setTimeout(() => { isIncidentActive = false; }, 5000);
});

modalDownloadBtn?.addEventListener("click", () => {
  window.location.href = API_BASE + "/api/report/generate";
});

// --- WS Logic Ext ---
function handleAction(action, type, risk, ts) {
  // If backend says auto-lock, trigger email check
  if (action === "auto_lock+siren") {
    sendEmailAlert(type, risk);
    // Trigger Visual Report immediately
    if (type === "weapon" || risk >= 90) {
      showAutoReport(type, risk, ts);
    }
  }
}

// --- WebSocket stream ---
function connectWS() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("WS connected");
    setRemoteStatus("Connected to backend.", "ONLINE");
  };

  // Throttling state
  let lastLogType = "";
  let lastLogTime = 0;
  let lastLogEl = null;

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === "ping") return;

    const risk = Number(data.risk_score ?? 0);
    const t = (data.type || "info").toLowerCase();
    const conf = data.confidence ?? 0;
    const ts = data.ts || "";
    const action = data.rule_action || "none";
    const cam = data.camera_id || "CAM-1";

    if (data.meta) { } // Hardware sync stub

    setRiskUI(risk);
    handleAction(action, t, risk, ts);

    // --- Log Logic ---
    let line = "";
    let cls = "muted";
    const personCount = data.meta?.person_count;

    if (t === "crowd") {
      line = `👥 CROWD | detected ${personCount}p`;
      cls = "warn";
    } else if (t === "weapon") {
      line = `🔫 WEAPON DETECTED`;
      cls = "danger";
    } else if (t === "mask") {
      line = risk > 80 ? `👺 MASK (LOITER)` : `😷 MASK DETECTED`;
      cls = risk > 80 ? "danger" : "warn";
    } else {
      line = `✅ NORMAL | Occupancy: ${personCount ?? 0}`;
      cls = "muted";
    }

    const fullLog = `[${cam}] ${ts} • ${line}`;
    const now = Date.now();

    // Throttle 1s
    if (t === lastLogType && (now - lastLogTime < 1000) && lastLogEl) {
      lastLogEl.textContent = fullLog + " (updating)";
      return;
    }

    clearMutedIfNeeded();
    lastLogEl = addDetectionLine(fullLog, cls);
    lastLogType = t;
    lastLogTime = now;

    if (action.includes("lock")) {
      setRemoteStatus("Security Action Triggered", "ALERT");
      // Explicit confirmation (with randomness to avoid spam if running 60fps)
      if (t !== "info" && Math.random() > 0.8) {
        addDetectionLine("🔒 AUTO-RESPONSE: Gate Locked & Alert Sent", "info");
      }
    }
  };

  // ...
  ws.onclose = () => {
    console.warn("WS closed. Reconnecting in 2s...");
    setRemoteStatus("Disconnected. Reconnecting...", "OFFLINE");
    setTimeout(connectWS, 2000);
  };

  ws.onerror = () => {
    setRemoteStatus("WebSocket error.", "ERROR");
  };
}
// init
connectWS();

connectWS();
