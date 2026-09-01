import { useEffect, useState } from "react";
import { Activity, Wifi, WifiOff, Clock, ShieldAlert } from "lucide-react";
import { MODE_STYLE } from "../../lib/format";

export default function Header({ mode, setMode, upstox, algoRunning, state, onEmergency, sessionActive }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const ist = now.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" });
  const modes = ["BACKTEST", "PAPER", "LIVE"];

  return (
    <header className="h-12 bg-[#111622] border-b border-[#243046] px-3 flex items-center gap-4 shrink-0 z-40 select-none" data-testid="top-header-bar">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 bg-blue-600 flex items-center justify-center">
          <Activity size={14} className="text-white" />
        </div>
        <span className="font-mono font-bold text-sm tracking-tight text-slate-100">QUANT-ROLLER<span className="text-blue-400"> PRO</span></span>
        <span className="text-[10px] font-mono text-slate-500 border border-slate-700 px-1 py-0.5">v2.4</span>
      </div>

      <div className="text-[11px] font-mono text-slate-500 hidden lg:block">Straddle ATR Band · Re-Centering Roller</div>

      <div className="flex-1" />

      {/* mode toggle */}
      <div className="flex border border-[#243046]" data-testid="trading-mode-selector">
        {modes.map((m) => (
          <button key={m} onClick={() => !sessionActive && setMode(m)} disabled={sessionActive}
            data-testid={`mode-${m.toLowerCase()}`}
            className={`px-3 py-1 text-[10px] font-mono font-bold tracking-wider border-r border-[#243046] last:border-r-0 transition-colors
              ${mode === m ? MODE_STYLE[m] : "text-slate-500 hover:text-slate-300"} ${sessionActive ? "cursor-not-allowed" : ""}`}>
            {m}
          </button>
        ))}
      </div>

      {/* upstox */}
      <div className="flex items-center gap-1.5" data-testid="upstox-status-indicator">
        {upstox?.connected ? <Wifi size={13} className="text-emerald-400" /> : <WifiOff size={13} className="text-slate-500" />}
        <span className={`text-[10px] font-mono font-semibold ${upstox?.connected ? "text-emerald-400" : "text-slate-500"}`}>
          UPSTOX {upstox?.connected ? "LINKED" : "OFFLINE"}
        </span>
      </div>

      {/* algo status */}
      <div className={`flex items-center gap-1.5 px-2 py-1 border text-[10px] font-mono font-bold
        ${algoRunning ? "border-emerald-700 bg-emerald-950/50 text-emerald-400" : "border-slate-700 text-slate-500"}`}
        data-testid="algo-status-badge">
        <span className={`w-1.5 h-1.5 rounded-full ${algoRunning ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
        ALGO {algoRunning ? "LIVE" : "IDLE"}
      </div>

      <div className="flex items-center gap-1.5 text-slate-300" data-testid="market-clock">
        <Clock size={13} className="text-slate-500" />
        <span className="font-mono text-xs tabular-nums">{ist} <span className="text-slate-600">IST</span></span>
      </div>

      <button onClick={onEmergency} data-testid="emergency-squareoff-header-btn"
        className="flex items-center gap-1.5 px-2.5 py-1.5 bg-red-950/70 border border-red-700 text-red-300 hover:bg-red-900 transition-colors text-[10px] font-mono font-bold">
        <ShieldAlert size={13} /> PANIC
      </button>
    </header>
  );
}
