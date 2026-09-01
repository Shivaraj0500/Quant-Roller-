const BASE = process.env.REACT_APP_BACKEND_URL;
const API = `${BASE}/api`;

async function req(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
  if (!res.ok) {
    const msg = data?.detail?.errors ? data.detail.errors.join(", ")
      : (typeof data?.detail === "string" ? data.detail : `Request failed (${res.status})`);
    throw new Error(msg);
  }
  return data;
}

export const api = {
  meta: () => req("/meta"),
  getConfig: () => req("/config"),
  saveConfig: (cfg) => req("/config", { method: "PUT", body: JSON.stringify(cfg) }),
  validate: (cfg) => req("/config/validate", { method: "POST", body: JSON.stringify(cfg) }),
  preview: (cfg) => req("/basket/preview", { method: "POST", body: JSON.stringify(cfg) }),
  backtest: (config, start, end) => req("/backtest/run", { method: "POST", body: JSON.stringify({ config, start, end }) }),
  sessionStart: (mode, config, confirmed = false) =>
    req("/session/start", { method: "POST", body: JSON.stringify({ mode, config, confirmed }) }),
  sessionStop: () => req("/session/stop", { method: "POST" }),
  sessionEmergency: () => req("/session/emergency", { method: "POST" }),
  sessionStatus: () => req("/session/status"),
  upstoxStatus: () => req("/upstox/status"),
  upstoxLogin: () => req("/upstox/login"),
  upstoxDisconnect: () => req("/upstox/disconnect", { method: "POST" }),
  upstoxFunds: () => req("/upstox/funds"),
  upstoxPositions: () => req("/upstox/positions"),
};
