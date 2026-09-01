import { fmt, money, pnlColor, STATE_STYLE } from "../../lib/format";

function Row({ label, value, cls = "" }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5">
      <span className="metric-label">{label}</span>
      <span className={`font-mono text-xs tabular-nums ${cls}`}>{value}</span>
    </div>
  );
}

const LEG_LABEL = { SHORT_CE: "SELL CE", SHORT_PE: "SELL PE", LONG_CE: "BUY CE HEDGE", LONG_PE: "BUY PE HEDGE" };
const LEG_TESTID = { SHORT_CE: "leg-short-ce-row", SHORT_PE: "leg-short-pe-row", LONG_CE: "leg-long-ce-row", LONG_PE: "leg-long-pe-row" };

export default function RightPanel({ status, funds }) {
  const s = status || {};
  const state = s.state || "WAITING";
  const basket = s.basket;
  const legs = basket?.legs || [];

  const fundData = funds?.data?.data?.equity || funds?.data?.equity || null;
  const avail = fundData?.available_margin;
  const used = fundData?.used_margin;

  return (
    <aside className="w-80 bg-[#111622] border-l border-[#243046] flex flex-col shrink-0 overflow-y-auto min-h-0 divide-y divide-[#243046]" data-testid="right-status-panel">
      {/* State */}
      <div>
        <div className="panel-header">Strategy Status</div>
        <div className="p-3">
          <div className={`inline-flex items-center gap-2 px-2.5 py-1 border font-mono text-[11px] font-bold tracking-wider ${STATE_STYLE[state] || STATE_STYLE.WAITING}`} data-testid="strategy-state-badge">
            <span className="w-1.5 h-1.5 rounded-full bg-current" /> {state}
          </div>
          {s.attention ? <div className="mt-2 text-[11px] font-mono text-yellow-400">{s.attention}</div> : null}
          <div className="mt-2 text-[11px] font-mono text-slate-500" data-testid="next-event-info">→ {s.next_event || "—"}</div>
        </div>
      </div>

      {/* Market / corridor */}
      <div>
        <Row label="Underlying" value={s.instrument || "—"} cls="text-slate-200" />
        <Row label="Spot" value={fmt(s.spot)} cls="text-slate-100 font-semibold" />
        <Row label="Center" value={fmt(s.center)} cls="text-sky-400" />
        <Row label="ATR × Mult" value={`${fmt(s.atr)} × ${fmt(s.atr_multiplier, 1)}`} cls="text-slate-300" />
        <Row label="Upper Boundary" value={fmt(s.upper)} cls="text-amber-400" />
        <Row label="Lower Boundary" value={fmt(s.lower)} cls="text-purple-300" />
      </div>

      {/* Basket P&L */}
      <div>
        <div className="panel-header">Basket P&amp;L (MTM)</div>
        <div className="px-3 py-3 flex items-baseline justify-between">
          <span className="metric-label">Net</span>
          <span className={`font-mono text-2xl font-bold tabular-nums ${pnlColor(s.basket_pnl)}`} data-testid="basket-pnl-display">
            {money(s.basket_pnl)}
          </span>
        </div>
      </div>

      {/* Four-leg basket */}
      <div data-testid="four-leg-basket-panel">
        <div className="panel-header">Current Basket · 4 Legs</div>
        {legs.length === 0 ? (
          <div className="px-3 py-4 text-[11px] font-mono text-slate-600">No active basket</div>
        ) : (
          <table className="blotter">
            <thead><tr><th>Leg</th><th>Strike</th><th>Avg</th><th>LTP</th><th>P&amp;L</th></tr></thead>
            <tbody>
              {legs.map((l, i) => (
                <tr key={i} data-testid={LEG_TESTID[l.role]}>
                  <td className={l.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{LEG_LABEL[l.role] || l.role}</td>
                  <td>{fmt(l.strike, 0)}</td>
                  <td>{fmt(l.avg_price)}</td>
                  <td>{fmt(l.ltp)}</td>
                  <td className={pnlColor(l.pnl)}>{money(l.pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Account / margin */}
      <div>
        <div className="panel-header">Account · Margin</div>
        {avail === undefined ? (
          <div className="px-3 py-3 text-[11px] font-mono text-slate-600">
            {funds?.connected === false ? "Connect Upstox to view live margin." : "Margin unavailable."}
          </div>
        ) : (
          <>
            <Row label="Available Margin" value={money(avail)} cls="text-slate-100" />
            <Row label="Used Margin" value={money(used)} cls="text-slate-300" />
          </>
        )}
        <div className="px-3 py-2">
          <div data-testid="account-available-margin" className="hidden">{avail}</div>
          <div data-testid="account-used-margin" className="hidden">{used}</div>
          <div className="text-[10px] font-mono text-slate-600">Margin benefit shown only when reported by Upstox.</div>
        </div>
      </div>
    </aside>
  );
}
