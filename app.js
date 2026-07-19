const statusPill = document.querySelector("#status-pill");
const statusLabel = document.querySelector("#status-label");
const refreshButton = document.querySelector("#refresh-status");
const panelTitle = document.querySelector("#panel-title");
const panelCopy = document.querySelector("#panel-copy");
const previewOnly = new URLSearchParams(window.location.search).has("preview");

function showState(state) {
  const checking = state === "checking";
  const online = state === "online";
  document.body.classList.toggle("is-online", online);
  document.body.classList.toggle("is-offline", state === "offline");
  statusPill.className = `status-pill ${state}`;
  statusLabel.textContent = checking ? "Wird geprüft …" : online ? "Online" : "Offline";

  if (checking) {
    panelTitle.textContent = "Studio wird gesucht …";
    panelCopy.textContent = "Die Verbindung zu deinem PC wird geprüft.";
  } else if (online) {
    panelTitle.textContent = "Studio ist online";
    panelCopy.textContent = "Die originale Oberfläche wird geöffnet …";
  } else {
    panelTitle.textContent = "Studio ist offline";
    panelCopy.textContent = "Öffne „Start Voice Cloning.bat“ auf deinem PC und prüfe den Status erneut.";
  }
}

async function appIsReachable(url) {
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
  showState("checking");
  refreshButton.disabled = true;
  try {
    const response = await fetch(`./status.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Status nicht erreichbar");
    const data = await response.json();
    const online = Boolean(data.online && data.url && await appIsReachable(data.url));
    showState(online ? "online" : "offline");
    if (online && !previewOnly) {
      window.setTimeout(() => window.location.replace(data.url), 450);
    }
  } catch {
    showState("offline");
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", refreshStatus);
refreshStatus();
