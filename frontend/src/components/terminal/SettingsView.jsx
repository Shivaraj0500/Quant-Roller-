import { useState } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { Link2, Unlink, RefreshCw, ShieldCheck, RotateCw, Copy, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";

const CALLBACK = `${process.env.REACT_APP_BACKEND_URL}/api/upstox/callback`;

function StatusDot({ ok }) {
  return ok ? <CheckCircle2 size={14} className="text-emerald-400" /> : <XCircle size={14} className="text-slate-500" />;
}
function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#243046]/60">
      <span className="metric-label">{label}</span>
      <span className="font-mono text-[11px] text-slate-200 flex items-center gap-2">{children}</span>
    </div>
  );
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " IST";
  } catch { return iso; }
}

export default function SettingsView({ upstox, refreshUpstox }) {
  const [busy, setBusy] = useState(false);
  const u = upstox || {};
  const missing = [];
  if (!u.api_key_present) missing.push("UPSTOX_API_KEY");
  if (!u.api_secret_present) missing.push("UPSTOX_API_SECRET");
  if (!u.redirect_present) missing.push("UPSTOX_REDIRECT_URI");

  const connect = async () => {
    setBusy(true);
    try {
      const { url } = await api.upstoxLogin();
      const win = window.open(url, "upstox-oauth", "width=520,height=720");
      const poll = setInterval(async () => {
        try {
          const st = await api.upstoxStatus();
          if (st.connected) { clearInterval(poll); win?.close(); refreshUpstox(); toast.success("Upstox connected"); }
        } catch { /* noop */ }
      }, 2500);
      setTimeout(() => clearInterval(poll), 180000);
    } catch (e) { toast.error(e.message); }
    setBusy(false);
  };
  const disconnect = async () => { await api.upstoxDisconnect(); refreshUpstox(); toast("Upstox disconnected"); };
  const copyCb = () => { navigator.clipboard?.writeText(CALLBACK); toast.success("Callback URL copied"); };

  const connected = u.connected;
  const needsReauth = u.has_token && u.token_expired;

  return (
    <div className="flex-1 overflow-auto p-4">
      <h2 className="font-mono text-lg font-bold tracking-tight text-slate-100 mb-1">UPSTOX SETTINGS</h2>
      <p className="text-xs text-slate-500 font-mono mb-4">Broker authentication for historical data, live data, option chain, positions, funds &amp; order execution.</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
        {/* Connection */}
        <div className="panel">
          <div className="panel-header">Connection
            <span className={`text-[10px] font-bold ${connected ? "text-emerald-400" : needsReauth ? "text-amber-400" : "text-slate-500"}`}>
              {connected ? "CONNECTED" : needsReauth ? "TOKEN EXPIRED" : "NOT CONNECTED"}
            </span>
          </div>
          <div className="p-4 space-y-1">
            <div className="flex items-center gap-3 pb-3">
              <div className={`w-2.5 h-2.5 rounded-full ${connected ? "bg-emerald-400" : needsReauth ? "bg-amber-400" : "bg-slate-600"}`} />
              <span className="font-mono text-sm text-slate-200" data-testid="upstox-connection-status">
                {connected ? "CONNECTED · live data available" : needsReauth ? "SESSION EXPIRED · re-authorize" : "NOT CONNECTED"}
              </span>
            </div>
            <Row label="Authentication"><StatusDot ok={connected} /> <span data-testid="upstox-token-status">{connected ? "Token active" : u.has_token ? "Token expired" : "No token"}</span></Row>
            <Row label="Last Connected"><span data-testid="upstox-last-connected">{fmtTime(u.issued_at)}</span></Row>
            <Row label="Token Expiry (03:30 IST)"><span data-testid="upstox-token-expiry">{fmtTime(u.expiry_at)}</span></Row>
            <Row label="Live-Data Availability"><StatusDot ok={connected} /> {connected ? "Available" : "Unavailable"}</Row>

            <div className="flex gap-2 pt-4">
              {!connected && !needsReauth && (
                <button className="btn-ctl !w-auto border-emerald-700 text-emerald-300 hover:bg-emerald-950" onClick={connect} disabled={busy || !u.configured} data-testid="btn-upstox-connect">
                  <Link2 size={13} /> Connect Upstox
                </button>
              )}
              {needsReauth && (
                <button className="btn-ctl !w-auto border-amber-700 text-amber-300 hover:bg-amber-950" onClick={connect} disabled={busy || !u.configured} data-testid="btn-upstox-reauthorize">
                  <RotateCw size={13} /> Re-authorize
                </button>
              )}
              {u.has_token && (
                <button className="btn-ctl !w-auto border-red-700 text-red-300 hover:bg-red-950" onClick={disconnect} data-testid="btn-upstox-disconnect">
                  <Unlink size={13} /> Disconnect
                </button>
              )}
              <button className="btn-ctl !w-auto border-slate-600 text-slate-300 hover:bg-slate-800" onClick={refreshUpstox} data-testid="btn-upstox-refresh">
                <RefreshCw size={13} /> Refresh
              </button>
            </div>
          </div>
        </div>

        {/* Server configuration */}
        <div className="panel">
          <div className="panel-header">Server Configuration
            <span className={`text-[10px] font-bold ${u.configured ? "text-emerald-400" : "text-amber-400"}`}>{u.configured ? "READY" : "INCOMPLETE"}</span>
          </div>
          <div className="p-4 space-y-1">
            <Row label="UPSTOX_API_KEY"><StatusDot ok={u.api_key_present} /> {u.api_key_present ? "Set" : "Missing"}</Row>
            <Row label="UPSTOX_API_SECRET"><StatusDot ok={u.api_secret_present} /> {u.api_secret_present ? "Set (hidden)" : "Missing"}</Row>
            <Row label="UPSTOX_REDIRECT_URI"><StatusDot ok={u.redirect_present} /> {u.redirect_present ? "Set" : "Missing"}</Row>

            <div className="pt-3">
              <div className="metric-label mb-1">Configured Redirect URI</div>
              <div className="font-mono text-[10.5px] text-slate-400 bg-[#0B0E14] border border-[#243046] p-2 break-all" data-testid="upstox-redirect-uri">{u.redirect_uri || "— not set —"}</div>
            </div>
            <div className="pt-2">
              <div className="metric-label mb-1 flex items-center justify-between">
                Expected Callback URL (register this in Upstox)
                <button onClick={copyCb} className="text-slate-400 hover:text-slate-200 flex items-center gap-1"><Copy size={11} /> copy</button>
              </div>
              <div className="font-mono text-[10.5px] text-blue-300 bg-[#0B0E14] border border-[#243046] p-2 break-all" data-testid="upstox-expected-callback">{CALLBACK}</div>
            </div>

            {!u.configured && (
              <div className="mt-3 border border-amber-800 bg-amber-950/40 p-3 text-[11px] font-mono text-amber-300 flex gap-2" data-testid="upstox-config-error">
                <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                <span>Missing server config: <b>{missing.join(", ")}</b>. Set these in <b>backend/.env</b> and restart the backend. The redirect URI must exactly match the callback URL above (as registered in the Upstox Developer Console).</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mt-4 panel p-3 flex items-start gap-2 text-[11px] font-mono text-slate-500">
        <ShieldCheck size={14} className="text-emerald-500 mt-0.5 shrink-0" />
        <span>Official Upstox OAuth authorization-code flow. The API secret and access token are stored encrypted server-side and are never sent to the browser or written to logs. Access tokens expire daily at 03:30 IST — re-authorize each trading day. Backtest and Paper modes do not require a connection.</span>
      </div>
    </div>
  );
}
