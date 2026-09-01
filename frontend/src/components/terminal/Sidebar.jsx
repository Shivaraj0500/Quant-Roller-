import { LayoutGrid, Sliders, FlaskConical, Layers, ScrollText, History, FileText, Settings, Play, Square, ShieldAlert } from "lucide-react";

const NAV = [
  { id: "terminal", label: "Terminal", icon: LayoutGrid, testid: "nav-terminal-tab" },
  { id: "strategy", label: "Strategy Config", icon: Sliders, testid: "nav-strategy-tab" },
  { id: "backtest", label: "Backtest Engine", icon: FlaskConical, testid: "nav-backtest-tab" },
  { id: "positions", label: "Positions", icon: Layers, testid: "nav-positions-tab" },
  { id: "orders", label: "Order Book", icon: ScrollText, testid: "nav-orders-tab" },
  { id: "trades", label: "Trade History", icon: History, testid: "nav-trades-tab" },
  { id: "logs", label: "System Logs", icon: FileText, testid: "nav-logs-tab" },
  { id: "settings", label: "Upstox Settings", icon: Settings, testid: "nav-settings-tab" },
];

export default function Sidebar({ active, setActive, mode, running, onStart, onStop, onEmergency, canStart }) {
  return (
    <aside className="w-56 bg-[#0E121B] border-r border-[#243046] flex flex-col justify-between shrink-0 select-none">
      <nav className="flex flex-col pt-2">
        {NAV.map((n) => {
          const Icon = n.icon;
          return (
            <div key={n.id} data-testid={n.testid}
              className={`nav-item ${active === n.id ? "active" : ""}`}
              onClick={() => setActive(n.id)}>
              <Icon size={15} /> {n.label}
            </div>
          );
        })}
      </nav>

      <div className="p-3 border-t border-[#243046] space-y-2">
        <div className="metric-label mb-1">Algo Controller · {mode}</div>
        <button className="btn-ctl border-emerald-800 text-emerald-400 hover:bg-emerald-950"
          onClick={onStart} disabled={running || !canStart} data-testid="btn-start-algo">
          <Play size={13} /> Start Algo
        </button>
        <button className="btn-ctl border-slate-700 text-slate-300 hover:bg-slate-800"
          onClick={onStop} disabled={!running} data-testid="btn-stop-algo">
          <Square size={13} /> Stop Algo
        </button>
        <button className="btn-ctl border-red-800 text-red-400 hover:bg-red-950"
          onClick={onEmergency} data-testid="btn-emergency-squareoff">
          <ShieldAlert size={13} /> Emergency Square-Off
        </button>
      </div>
    </aside>
  );
}
