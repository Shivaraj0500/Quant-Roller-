import { useState } from "react";
import { toast } from "sonner";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../../lib/api";
import { fmt, money, pnlColor, hhmm } from "../../lib/format";
import { Play, Loader2 } from "lucide-react";

const inputCls = "bg-[#0B0E14] border border-[#243046] px-2 py-1.5 text-xs font-mono text-slate-100 focus:border-blue-500 focus:outline-none";

function Stat({ label, value, cls = "text-slate-100" }) {
  return (
    <div className="panel p-3">
      <div className="metric-label">{label}</div>
      <div className={`font-mono text-lg font-bold tabular-nums mt-1 ${cls}`}>{value}</div>
    </div>
  );
}

export default function BacktestView({ config }) {
  const today = new Date();
  const d14 = new Date(today.getTime() - 14 * 864e5);
  const [start, setStart] = useState(d14.toISOString().slice(0, 10));
  const [end, setEnd] = useState(today.toISOString().slice(0, 10));
  const [running, setRunning] = useState(false);
  const [res, setRes] = useState(null);

  const run = async () => {
    setRunning(true);
    try {
      const r = await api.backtest(config, start, end);
      setRes(r);
      toast.success(`Backtest complete · ${r.stats.total_baskets} baskets`);
    } catch (e) { toast.error(e.message); }
    setRunning(false);
  };

  const s = res?.stats;

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="font-mono text-lg font-bold tracking-tight text-slate-100">BACKTEST ENGINE</h2>
          <p className="text-xs text-slate-500 font-mono">{config.instrument} · {config.timeframe}m · shared strategy engine</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex flex-col gap-1"><span className="metric-label">From</span><input type="date" className={inputCls} value={start} onChange={(e) => setStart(e.target.value)} data-testid="bt-start" /></label>
          <label className="flex flex-col gap-1"><span className="metric-label">To</span><input type="date" className={inputCls} value={end} onChange={(e) => setEnd(e.target.value)} data-testid="bt-end" /></label>
          <button className="btn-ctl !w-auto border-blue-700 text-blue-300 hover:bg-blue-950" onClick={run} disabled={running} data-testid="btn-run-backtest">
            {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run Backtest
          </button>
        </div>
      </div>

      {!res ? (
        <div className="panel p-10 text-center text-slate-600 font-mono text-sm">Configure the strategy, choose a date range and run the backtest.</div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3" data-testid="backtest-stats">
            <Stat label="Total P&L" value={money(s.total_pnl)} cls={pnlColor(s.total_pnl)} />
            <Stat label="Baskets" value={s.total_baskets} />
            <Stat label="Wins" value={s.winning_baskets} cls="text-emerald-400" />
            <Stat label="Losses" value={s.losing_baskets} cls="text-red-400" />
            <Stat label="Win Rate" value={`${s.win_rate}%`} />
            <Stat label="Max DD" value={money(s.max_drawdown)} cls="text-red-400" />
            <Stat label="Roll Up" value={s.roll_up_count} cls="text-amber-400" />
            <Stat label="Roll Down" value={s.roll_down_count} cls="text-purple-300" />
          </div>

          <div className="panel">
            <div className="panel-header">Equity Curve (Cumulative Realized P&amp;L)</div>
            <div className="p-3 h-64" data-testid="equity-curve">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={res.equity.map((e, i) => ({ i, equity: e.equity }))}>
                  <CartesianGrid stroke="#1a2234" />
                  <XAxis dataKey="i" tick={{ fill: "#475569", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#475569", fontSize: 10 }} width={60} />
                  <Tooltip contentStyle={{ background: "#111622", border: "1px solid #243046", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                  <Line type="monotone" dataKey="equity" stroke="#3B82F6" dot={false} strokeWidth={1.6} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="panel">
              <div className="panel-header">Daily P&amp;L</div>
              <div className="max-h-72 overflow-auto">
                <table className="blotter"><thead><tr><th>Date</th><th>P&amp;L</th></tr></thead>
                  <tbody>{Object.entries(res.daily_pnl).map(([d, p]) => (
                    <tr key={d}><td>{d}</td><td className={pnlColor(p)}>{money(p)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
            <div className="panel">
              <div className="panel-header">Event Log</div>
              <div className="max-h-72 overflow-auto">
                <table className="blotter"><thead><tr><th>Time</th><th>Event</th><th>Reason</th></tr></thead>
                  <tbody>{res.events.slice(0, 200).map((e, i) => (
                    <tr key={i}><td>{hhmm(e.ts)}</td><td className="font-bold text-slate-200">{e.type}</td><td className="text-left text-slate-400">{e.reason}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">Basket History</div>
            <div className="max-h-96 overflow-auto">
              <table className="blotter">
                <thead><tr><th>Day</th><th>Event</th><th>Entry</th><th>Exit</th><th>Center</th><th>CE / PE</th><th>Hedge CE / PE</th><th>P&amp;L</th><th>Close Reason</th></tr></thead>
                <tbody>
                  {res.baskets.map((b, i) => {
                    const ce = b.legs.find((l) => l.role === "SHORT_CE");
                    const pe = b.legs.find((l) => l.role === "SHORT_PE");
                    const hce = b.legs.find((l) => l.role === "LONG_CE");
                    const hpe = b.legs.find((l) => l.role === "LONG_PE");
                    return (
                      <tr key={i}>
                        <td>{b.day}</td><td className="font-semibold text-slate-300">{b.open_event}</td>
                        <td>{hhmm(b.entry_ts)}</td><td>{hhmm(b.exit_ts)}</td><td>{fmt(b.center, 0)}</td>
                        <td>{ce ? fmt(ce.strike, 0) : "—"} / {pe ? fmt(pe.strike, 0) : "—"}</td>
                        <td>{hce ? fmt(hce.strike, 0) : "—"} / {hpe ? fmt(hpe.strike, 0) : "—"}</td>
                        <td className={pnlColor(b.pnl)}>{money(b.pnl)}</td>
                        <td className="text-left text-slate-500">{b.close_reason}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="text-[10px] font-mono text-slate-600">{res.meta?.note}</div>
        </div>
      )}
    </div>
  );
}
