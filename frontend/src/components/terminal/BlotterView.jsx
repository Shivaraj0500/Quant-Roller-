import { fmt, money, pnlColor, hhmm } from "../../lib/format";

export default function BlotterView({ view, status }) {
  const s = status || {};
  const legs = s.basket?.legs || [];
  const titles = { positions: "POSITIONS BLOTTER", orders: "ORDER BOOK", trades: "TRADE HISTORY", logs: "SYSTEM LOGS" };

  return (
    <div className="flex-1 overflow-auto p-4">
      <h2 className="font-mono text-lg font-bold tracking-tight text-slate-100 mb-1">{titles[view]}</h2>
      <p className="text-xs text-slate-500 font-mono mb-4">{s.mode || "—"} session · {s.instrument || "—"}</p>

      <div className="panel">
        {view === "positions" && (
          <table className="blotter">
            <thead><tr><th>Leg</th><th>Type</th><th>Side</th><th>Strike</th><th>Expiry</th><th>Qty</th><th>Avg Price</th><th>LTP</th><th>P&amp;L</th><th>Order Status</th></tr></thead>
            <tbody>{legs.length === 0 ? <E c={10} /> : legs.map((l, i) => (
              <tr key={i} data-testid="position-table-row">
                <td>{l.role}</td><td>{l.type}</td><td className={l.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{l.side}</td>
                <td>{fmt(l.strike, 0)}</td><td className="text-slate-500">{l.expiry}</td><td>{l.qty}</td>
                <td>{fmt(l.avg_price)}</td><td>{fmt(l.ltp)}</td><td className={pnlColor(l.pnl)}>{money(l.pnl)}</td><td className="text-emerald-400">{l.status}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
        {view === "orders" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Event</th><th>Leg</th><th>Side</th><th>Strike</th><th>Qty</th><th>Price</th><th>Status</th><th>Order ID</th></tr></thead>
            <tbody>{(s.orders || []).length === 0 ? <E c={9} /> : s.orders.map((o, i) => (
              <tr key={i} data-testid="order-table-row"><td>{hhmm(o.ts)}</td><td className="text-slate-400">{o.event}</td><td>{o.leg}</td>
                <td className={o.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{o.side}</td><td>{fmt(o.strike, 0)}</td><td>{o.qty}</td><td>{fmt(o.price)}</td>
                <td className={o.status === "COMPLETE" ? "text-emerald-400" : o.status === "REJECTED" ? "text-red-400" : "text-amber-400"}>{o.status}</td><td className="text-slate-500">{o.order_id || "—"}</td></tr>
            ))}</tbody>
          </table>
        )}
        {view === "trades" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Leg</th><th>Side</th><th>Strike</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&amp;L</th><th>Reason</th></tr></thead>
            <tbody>{(s.trades || []).length === 0 ? <E c={9} /> : s.trades.map((t, i) => (
              <tr key={i}><td>{hhmm(t.ts)}</td><td>{t.leg}</td><td className={t.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{t.side}</td>
                <td>{fmt(t.strike, 0)}</td><td>{t.qty}</td><td>{fmt(t.entry)}</td><td>{fmt(t.exit)}</td><td className={pnlColor(t.pnl)}>{money(t.pnl)}</td><td className="text-left text-slate-500">{t.reason}</td></tr>
            ))}</tbody>
          </table>
        )}
        {view === "logs" && (
          <table className="blotter">
            <thead><tr><th>Time</th><th>Type</th><th>Detail</th></tr></thead>
            <tbody>
              {[...(s.errors || []).map((e) => ({ ...e, err: true })), ...(s.events || [])].sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 300).map((e, i) => (
                <tr key={i}><td>{hhmm(e.ts)}</td><td className={e.err ? "text-red-400" : "text-slate-200 font-semibold"}>{e.type}</td><td className="text-left text-slate-400">{e.reason}</td></tr>
              ))}
              {(!s.events?.length && !s.errors?.length) ? <E c={3} /> : null}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
const E = ({ c }) => <tr><td colSpan={c} style={{ textAlign: "center" }} className="py-8 text-slate-600">No records</td></tr>;
