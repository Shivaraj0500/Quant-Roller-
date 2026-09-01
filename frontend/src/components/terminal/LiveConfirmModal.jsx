import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { fmt, money } from "../../lib/format";

export default function LiveConfirmModal({ config, preview, onConfirm, onCancel }) {
  const [ack, setAck] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" data-testid="live-mode-confirm-modal">
      <div className="w-[560px] max-w-[95vw] bg-[#111622] border border-red-700">
        <div className="flex items-center justify-between px-4 py-3 bg-red-950/60 border-b border-red-800">
          <div className="flex items-center gap-2 text-red-300 font-mono font-bold text-sm">
            <AlertTriangle size={16} /> LIVE TRADING CONFIRMATION
          </div>
          <button onClick={onCancel} className="text-slate-400 hover:text-white"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-2 text-[12px] font-mono">
            <KV k="Mode" v="LIVE" vc="text-red-400" />
            <KV k="Broker" v="UPSTOX" />
            <KV k="Instrument" v={config.instrument} />
            <KV k="Expiry" v={preview?.expiry || config.expiry || "nearest"} />
            <KV k="Entry / Exit" v={`${config.entry_time} / ${config.exit_time}`} />
            <KV k="Lots × Qty" v={`${config.lots} × ${preview?.total_qty ?? "—"}`} />
            <KV k="ADX < / ATR ×" v={`${config.adx_threshold} / ${config.atr_multiplier}`} />
            <KV k="Short Method" v={config.short_method} />
          </div>

          {preview?.legs && (
            <table className="blotter border border-[#243046]">
              <thead><tr><th>Leg</th><th>Strike</th><th>Prem</th></tr></thead>
              <tbody>{preview.legs.map((l, i) => (
                <tr key={i}><td className={l.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{l.side} {l.type}</td><td>{fmt(l.strike, 0)}</td><td>{fmt(l.premium)}</td></tr>
              ))}</tbody>
            </table>
          )}

          <div className="bg-red-950/40 border border-red-800 p-3 text-[12px] font-mono text-red-300 font-bold text-center">
            REAL ORDERS WILL BE SUBMITTED TO UPSTOX.
          </div>

          <label className="flex items-center gap-2 text-[12px] font-mono text-slate-300 cursor-pointer">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} data-testid="live-mode-confirm-checkbox" />
            I understand this will place real, capital-at-risk orders.
          </label>
        </div>
        <div className="flex gap-2 p-4 border-t border-[#243046]">
          <button className="btn-ctl border-slate-600 text-slate-300 hover:bg-slate-800" onClick={onCancel}>Cancel</button>
          <button className="btn-ctl border-red-700 text-red-300 hover:bg-red-900 disabled:opacity-40" disabled={!ack} onClick={onConfirm} data-testid="live-mode-confirm-submit">
            ARM LIVE ALGO
          </button>
        </div>
      </div>
    </div>
  );
}
function KV({ k, v, vc = "text-slate-100" }) {
  return <div className="flex justify-between border-b border-[#243046]/60 py-1"><span className="text-slate-500">{k}</span><span className={vc}>{v}</span></div>;
}
