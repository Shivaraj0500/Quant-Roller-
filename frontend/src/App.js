import { useEffect, useState, useCallback, useRef } from "react";
import { Toaster, toast } from "sonner";
import "@/App.css";
import { api } from "@/lib/api";
import Header from "@/components/terminal/Header";
import Sidebar from "@/components/terminal/Sidebar";
import CandleChart from "@/components/terminal/CandleChart";
import RightPanel from "@/components/terminal/RightPanel";
import BottomTerminal from "@/components/terminal/BottomTerminal";
import StrategyConfigView from "@/components/terminal/StrategyConfigView";
import BacktestView from "@/components/terminal/BacktestView";
import SettingsView from "@/components/terminal/SettingsView";
import BlotterView from "@/components/terminal/BlotterView";
import LiveConfirmModal from "@/components/terminal/LiveConfirmModal";
import { MODE_STYLE, fmt } from "@/lib/format";

export default function App() {
  const [meta, setMeta] = useState(null);
  const [config, setConfig] = useState(null);
  const [mode, setMode] = useState("PAPER");
  const [active, setActive] = useState("terminal");
  const [upstox, setUpstox] = useState({ configured: false, connected: false });
  const [funds, setFunds] = useState(null);
  const [status, setStatus] = useState(null);
  const [showLive, setShowLive] = useState(false);
  const [livePreview, setLivePreview] = useState(null);
  const [interval, setIntervalTf] = useState(5);

  const refreshUpstox = useCallback(async () => {
    try {
      const st = await api.upstoxStatus();
      setUpstox(st);
      if (st.connected) { try { setFunds(await api.upstoxFunds()); } catch { /* noop */ } }
    } catch { /* noop */ }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [m, c] = await Promise.all([api.meta(), api.getConfig()]);
        setMeta(m); setConfig(c); setIntervalTf(c.timeframe);
      } catch (e) { toast.error("Failed to load: " + e.message); }
    })();
    refreshUpstox();
  }, [refreshUpstox]);

  // poll session status
  useEffect(() => {
    let alive = true;
    const tick = async () => { try { const s = await api.sessionStatus(); if (alive) setStatus(s); } catch { /* noop */ } };
    tick();
    const t = setInterval(tick, 1500);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const running = status?.running;
  const sessionActive = running || (status?.state && status.state !== "WAITING" && status?.mode);

  const doStart = async () => {
    if (!config) return;
    if (mode === "LIVE") {
      if (!upstox.connected) { toast.error("Connect Upstox first (Settings)"); setActive("settings"); return; }
      try { setLivePreview(await api.preview(config)); } catch { /* noop */ }
      setShowLive(true);
      return;
    }
    try { await api.sessionStart(mode, config); toast.success(`${mode} session started`); setActive("terminal"); }
    catch (e) { toast.error(e.message); }
  };
  const confirmLive = async () => {
    setShowLive(false);
    try { await api.sessionStart("LIVE", config, true); toast.success("LIVE algo armed"); setActive("terminal"); }
    catch (e) { toast.error(e.message); }
  };
  const doStop = async () => { try { await api.sessionStop(); toast("Algo stopped"); } catch (e) { toast.error(e.message); } };
  const doEmergency = async () => {
    if (!window.confirm("EMERGENCY SQUARE-OFF — close all legs immediately?")) return;
    try { await api.sessionEmergency(); toast.error("Emergency square-off executed"); } catch (e) { toast.error(e.message); }
  };

  if (!config || !meta) {
    return <div className="h-full flex items-center justify-center text-slate-500 font-mono text-sm">Initializing QUANT-ROLLER PRO…</div>;
  }

  const s = status || {};

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0B0E14] text-slate-100">
      <Toaster theme="dark" position="top-right" toastOptions={{ style: { background: "#111622", border: "1px solid #243046", color: "#F1F5F9", fontFamily: "JetBrains Mono", fontSize: "12px" } }} />
      <Header mode={mode} setMode={setMode} upstox={upstox} algoRunning={running} state={s.state}
        onEmergency={doEmergency} sessionActive={sessionActive} />

      <div className="flex flex-1 overflow-hidden min-h-0">
        <Sidebar active={active} setActive={setActive} mode={mode} running={running}
          onStart={doStart} onStop={doStop} onEmergency={doEmergency}
          canStart={!!config && (mode !== "LIVE" || upstox.connected)} />

        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* LIVE mode banner */}
          {mode === "LIVE" && (
            <div className={`px-3 py-1.5 border-b text-[11px] font-mono font-bold text-center ${MODE_STYLE.LIVE}`}>
              ⚠ LIVE MODE — REAL ORDERS WILL BE SUBMITTED TO UPSTOX
            </div>
          )}

          {active === "terminal" && (
            <>
              <div className="flex-1 flex min-h-0 overflow-hidden">
                <div className="flex-1 flex flex-col min-w-0 border-r border-[#243046] relative">
                  <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#243046] bg-[#0E121B]">
                    <span className="font-mono text-xs font-bold text-slate-200">{s.instrument || config.instrument}</span>
                    <span className="font-mono text-xs text-slate-400 tabular-nums">{fmt(s.spot)}</span>
                    <div className="flex-1" />
                    <div className="flex border border-[#243046]">
                      {(meta.timeframes || [1,3,5,15]).map((tf) => (
                        <button key={tf} data-testid={`chart-interval-${tf}m`}
                          onClick={() => { if (!running) { setIntervalTf(tf); setConfig({ ...config, timeframe: tf }); } }}
                          className={`px-2 py-0.5 text-[10px] font-mono font-bold border-r border-[#243046] last:border-r-0 ${config.timeframe === tf ? "bg-blue-950 text-blue-300" : "text-slate-500 hover:text-slate-300"}`}>
                          {tf}m
                        </button>
                      ))}
                    </div>
                    <span className="text-[10px] font-mono text-slate-600 ml-2">ATR bands · center · markers</span>
                    {s.data_source && (running || s.state !== "WAITING") ? (
                      <span data-testid="data-source-badge" className={`ml-2 px-2 py-0.5 text-[9.5px] font-mono font-bold border ${s.data_source === "UPSTOX" ? "border-emerald-700 text-emerald-400 bg-emerald-950/40" : "border-slate-600 text-slate-400"}`}>
                        DATA: {s.data_source}{s.expiry ? ` · ${s.expiry}` : ""}
                      </span>
                    ) : null}
                  </div>
                  <CandleChart candles={s.candles || []} center={s.center} upper={s.upper} lower={s.lower} events={s.events || []} spot={s.spot} />
                </div>
                <RightPanel status={s} funds={funds} />
              </div>
              <BottomTerminal status={s} />
            </>
          )}

          {active === "strategy" && <StrategyConfigView config={config} setConfig={setConfig} meta={meta} />}
          {active === "backtest" && <BacktestView config={config} />}
          {active === "settings" && <SettingsView upstox={upstox} refreshUpstox={refreshUpstox} />}
          {["positions", "orders", "trades", "logs"].includes(active) && <BlotterView view={active} status={s} />}
        </main>
      </div>

      {showLive && <LiveConfirmModal config={config} preview={livePreview} onConfirm={confirmLive} onCancel={() => setShowLive(false)} />}
    </div>
  );
}
