const STATUS_URL = "./status.json";

const pill = document.querySelector("#status-pill");
const pillLabel = document.querySelector("#status-label");
const cardState = document.querySelector("#card-state");
const cardTitle = document.querySelector("#card-title");
const heroCopy = document.querySelector("#hero-copy");
const lastUpdate = document.querySelector("#last-update");
const openButton = document.querySelector("#open-app");
const refreshButton = document.querySelector("#refresh-status");

function setState(state, data = {}) {
  const online = state === "online";
  const checking = state === "checking";
  const label = checking ? "Status wird geprüft" : online ? "Online" : "Offline";

  pill.className = `status-pill ${state}`;
  cardState.className = `card-state ${state}`;
  pillLabel.textContent = label;
  cardState.querySelector("span:last-child").textContent = checking ? "Prüfen" : label;

  if (checking) {
    cardTitle.textContent = "Studio wird gesucht …";
    return;
  }

  if (online && data.url) {
    cardTitle.textContent = "Dein Studio ist online";
    heroCopy.textContent = "Die App läuft gerade auf deinem PC und ist über eine geschützte Verbindung erreichbar.";
    openButton.href = data.url;
    openButton.target = "_blank";
    openButton.rel = "noopener noreferrer";
    openButton.classList.remove("disabled");
    openButton.setAttribute("aria-disabled", "false");
  } else {
    cardTitle.textContent = "Dein Studio ist offline";
    heroCopy.textContent = "Öffne „Start Voice Cloning.bat“ auf deinem PC. Sobald das Modell bereit ist, erscheint hier der Online-Status.";
    openButton.href = "#";
    openButton.removeAttribute("target");
    openButton.classList.add("disabled");
    openButton.setAttribute("aria-disabled", "true");
  }

  if (data.updated_at) {
    const updated = new Date(data.updated_at);
    lastUpdate.textContent = new Intl.DateTimeFormat("de-DE", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(updated);
  } else {
    lastUpdate.textContent = "Noch keine Daten";
  }
}

async function probeApp(url) {
  if (!url) return false;
  try {
    const response = await fetch(`${url.replace(/\/$/, "")}/gradio_api/info`, {
      method: "GET",
      cache: "no-store",
      headers: { "ngrok-skip-browser-warning": "1" },
    });
    return response.ok || response.status === 401;
  } catch {
    return false;
  }
}

async function refreshStatus() {
  setState("checking");
  refreshButton.disabled = true;
  try {
    const response = await fetch(`${STATUS_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Status nicht erreichbar");
    const data = await response.json();
    const online = Boolean(data.online && data.url && await probeApp(data.url));
    setState(online ? "online" : "offline", data);
  } catch {
    setState("offline");
  } finally {
    refreshButton.disabled = false;
  }
}

openButton.addEventListener("click", (event) => {
  if (openButton.classList.contains("disabled")) event.preventDefault();
});
refreshButton.addEventListener("click", refreshStatus);

refreshStatus();
window.setInterval(refreshStatus, 15000);
