import { useState } from "react";
import { fmt, money, pnlColor, hhmm } from "../../lib/format";

const TABS = [
  { id: "orders", label: "Orders", testid: "tab-orders-list" },
  { id: "positions", label: "Positions", testid: "tab-positions-list" },
  { id: "trades", label: "Trades", testid: "tab-trades-list" },
  { id: "events", label: "Events", testid: "tab-events-log" },
  { id: "errors", label: "Errors", testid: "tab-errors-log" },
];

export default function BottomTerminal({ status }) {
  const [tab, setTab] = useState("orders");
  const s = status || {};
  const orders = s.orders || [];
  const trades = s.trades || [];
  const events = s.events || [];
  const errors = s.errors || [];
  const legs = s.basket?.legs || [];

  return (
    <div className="h-64 bg-[#0E121B] border-t border-[#243046] flex flex-col shrink-0 min-w-0 overflow-hidden" data-testid="execution-terminal">
      <div className="flex items-center border-b border-[#243046] bg-[#111622]" data-testid="execution-terminal-tabs">
        {TABS.map((t) => (
          <button key={t.id} data-testid={t.testid} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-[11px] font-mono font-bold uppercase tracking-wider border-r border-[#243046] transition-colors
              ${tab === t.id ? "text-slate-100 bg-[#151C2C] border-b-2 border-b-blue-500" : "text-slate-500 hover:text-slate-300"}`}>
            {t.label}
            {t.id === "errors" && errors.length ? <span className="ml-1.5 text-red-400">({errors.length})</span> : null}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto">
        {tab === "orders" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Event</th><th>Leg</th><th>Side</th><th>Strike</th><th>Qty</th><th>Price</th><th>Status</th><th>Order ID</th></tr></thead>
            <tbody>
              {orders.length === 0 ? <Empty cols={9} /> : orders.map((o, i) => (
                <tr key={i} data-testid="order-table-row">
                  <td>{hhmm(o.ts)}</td><td className="text-slate-400">{o.event}</td>
                  <td>{o.leg}</td>
                  <td className={o.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{o.side}</td>
                  <td>{fmt(o.strike, 0)}</td><td>{o.qty}</td><td>{fmt(o.price)}</td>
                  <td className={o.status === "COMPLETE" ? "text-emerald-400" : o.status === "REJECTED" ? "text-red-400" : "text-amber-400"}>{o.status}</td>
                  <td className="text-slate-500">{o.order_id || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "positions" && (
          <table className="blotter">
            <thead><tr><th>Leg</th><th>Type</th><th>Side</th><th>Strike</th><th>Expiry</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&amp;L</th><th>Status</th></tr></thead>
            <tbody>
              {legs.length === 0 ? <Empty cols={10} /> : legs.map((l, i) => (
                <tr key={i} data-testid="position-table-row">
                  <td>{l.role}</td><td>{l.type}</td>
                  <td className={l.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{l.side}</td>
                  <td>{fmt(l.strike, 0)}</td><td className="text-slate-500">{l.expiry}</td><td>{l.qty}</td>
                  <td>{fmt(l.avg_price)}</td><td>{fmt(l.ltp)}</td>
                  <td className={pnlColor(l.pnl)}>{money(l.pnl)}</td>
                  <td className="text-emerald-400">{l.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "trades" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Leg</th><th>Side</th><th>Strike</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&amp;L</th><th>Reason</th></tr></thead>
            <tbody>
              {trades.length === 0 ? <Empty cols={9} /> : trades.map((t, i) => (
                <tr key={i}>
                  <td>{hhmm(t.ts)}</td><td>{t.leg}</td>
                  <td className={t.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{t.side}</td>
                  <td>{fmt(t.strike, 0)}</td><td>{t.qty}</td><td>{fmt(t.entry)}</td><td>{fmt(t.exit)}</td>
                  <td className={pnlColor(t.pnl)}>{money(t.pnl)}</td>
                  <td className="text-slate-500">{t.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "events" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Event</th><th>Center</th><th>Upper</th><th>Lower</th><th>Reason</th></tr></thead>
            <tbody>
              {events.length === 0 ? <Empty cols={6} /> : events.map((e, i) => (
                <tr key={i}>
                  <td>{hhmm(e.ts)}</td>
                  <td className="font-bold text-slate-200">{e.type}</td>
                  <td>{e.center ? fmt(e.center) : "—"}</td><td>{e.upper ? fmt(e.upper) : "—"}</td><td>{e.lower ? fmt(e.lower) : "—"}</td>
                  <td className="text-slate-400 text-left">{e.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {tab === "errors" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Type</th><th>Reason</th></tr></thead>
            <tbody>
              {errors.length === 0 ? <Empty cols={3} msg="No errors — execution healthy" /> : errors.map((e, i) => (
                <tr key={i}><td>{hhmm(e.ts)}</td><td className="text-red-400">{e.type}</td><td className="text-left text-red-300">{e.reason}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Empty({ cols, msg = "No records" }) {
  return <tr><td colSpan={cols} className="text-center text-slate-600 py-6 !text-left" style={{ textAlign: "center" }}>{msg}</td></tr>;
}
