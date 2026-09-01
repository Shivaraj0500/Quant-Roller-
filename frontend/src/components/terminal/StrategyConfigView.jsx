import { useState } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { fmt, money } from "../../lib/format";
import { Save, Eye } from "lucide-react";

const inputCls = "bg-[#0B0E14] border border-[#243046] px-2 py-1.5 text-xs font-mono text-slate-100 w-full focus:border-blue-500 focus:outline-none tabular-nums";

function Field({ label, children, hint }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="metric-label">{label}</span>
      {children}
      {hint ? <span className="text-[9.5px] text-slate-600 font-mono">{hint}</span> : null}
    </label>
  );
}
function Section({ title, children, cols = 2 }) {
  return (
    <div className="panel">
      <div className="panel-header">{title}</div>
      <div className={`p-3 grid gap-3`} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }}>{children}</div>
    </div>
  );
}

export default function StrategyConfigView({ config, setConfig, meta }) {
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setConfig({ ...config, [k]: v });
  const num = (k, v) => set(k, v === "" ? "" : Number(v));

  const lotSize = meta?.instruments?.[config.instrument]?.lot_size || 0;

  const save = async () => {
    setSaving(true);
    try {
      const v = await api.validate(config);
      if (!v.valid) { toast.error(v.errors.join(", ")); setSaving(false); return; }
      await api.saveConfig(config);
      toast.success("Strategy configuration saved");
    } catch (e) { toast.error(e.message); }
    setSaving(false);
  };
  const doPreview = async () => {
    try { const p = await api.preview(config); setPreview(p); toast.success("Basket preview generated"); }
    catch (e) { toast.error(e.message); }
  };

  const Sel = ({ k, opts }) => (
    <select className={inputCls} value={config[k]} onChange={(e) => set(k, isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value))} data-testid={`cfg-${k}`}>
      {opts.map((o) => <option key={o.v ?? o} value={o.v ?? o}>{o.l ?? o}</option>)}
    </select>
  );

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-mono text-lg font-bold tracking-tight text-slate-100">STRATEGY CONFIGURATION</h2>
          <p className="text-xs text-slate-500 font-mono">Straddle ATR Band — Re-Centering Roller</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ctl !w-auto border-slate-600 text-slate-200 hover:bg-slate-800" onClick={doPreview} data-testid="btn-preview-basket"><Eye size={13} /> Preview Basket</button>
          <button className="btn-ctl !w-auto border-blue-700 text-blue-300 hover:bg-blue-950" onClick={save} disabled={saving} data-testid="btn-save-config"><Save size={13} /> {saving ? "Saving…" : "Save Config"}</button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4 xl:col-span-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Section title="Strategy">
              <Field label="Instrument"><Sel k="instrument" opts={Object.keys(meta?.instruments || { NIFTY: 1 })} /></Field>
              <Field label="Expiry" hint="Blank = nearest weekly">
                <input className={inputCls} placeholder="YYYY-MM-DD / nearest" value={config.expiry || ""} onChange={(e) => set("expiry", e.target.value || null)} data-testid="cfg-expiry" />
              </Field>
              <Field label="Timeframe (min)"><Sel k="timeframe" opts={(meta?.timeframes || [1,3,5,15]).map((t) => ({ v: t, l: `${t}m` }))} /></Field>
              <Field label="Center Source"><Sel k="center_source" opts={meta?.center_sources || ["CLOSE","OPEN"]} /></Field>
            </Section>

            <Section title="Indicators">
              <Field label="ADX Period" hint="impl default 14 (editable)"><input type="number" className={inputCls} value={config.adx_period} onChange={(e) => num("adx_period", e.target.value)} data-testid="cfg-adx_period" /></Field>
              <Field label="ADX Threshold" hint="strategy default 22"><input type="number" className={inputCls} value={config.adx_threshold} onChange={(e) => num("adx_threshold", e.target.value)} data-testid="cfg-adx_threshold" /></Field>
              <Field label="ATR Period" hint="impl default 14 (editable)"><input type="number" className={inputCls} value={config.atr_period} onChange={(e) => num("atr_period", e.target.value)} data-testid="cfg-atr_period" /></Field>
              <Field label="ATR Multiplier" hint="strategy default 2.0"><input type="number" step="0.1" className={inputCls} value={config.atr_multiplier} onChange={(e) => num("atr_multiplier", e.target.value)} data-testid="cfg-atr_multiplier" /></Field>
            </Section>

            <Section title="Timing (IST)">
              <Field label="Initial Entry Time" hint="strategy default 09:30"><input className={inputCls} value={config.entry_time} onChange={(e) => set("entry_time", e.target.value)} data-testid="cfg-entry_time" /></Field>
              <Field label="Exit Time" hint="mandatory square-off"><input className={inputCls} value={config.exit_time} onChange={(e) => set("exit_time", e.target.value)} data-testid="cfg-exit_time" /></Field>
            </Section>

            <Section title="Position Size">
              <Field label="Lots"><input type="number" min="1" className={inputCls} value={config.lots} onChange={(e) => num("lots", e.target.value)} data-testid="cfg-lots" /></Field>
              <Field label="Lot Size × Lots = Qty">
                <div className={`${inputCls} !text-emerald-400 flex items-center`}>{lotSize} × {config.lots} = {lotSize * config.lots}</div>
              </Field>
            </Section>
          </div>

          <Section title="Short Legs" cols={3}>
            <Field label="Selection Method"><Sel k="short_method" opts={meta?.short_methods || ["ATM","OTM","DELTA","PREMIUM"]} /></Field>
            {config.short_method === "OTM" && (<>
              <Field label="Short CE OTM (steps)" hint="ladder steps from ATM"><input type="number" className={inputCls} value={config.short_ce_otm} onChange={(e) => num("short_ce_otm", e.target.value)} data-testid="cfg-short_ce_otm" /></Field>
              <Field label="Short PE OTM (steps)"><input type="number" className={inputCls} value={config.short_pe_otm} onChange={(e) => num("short_pe_otm", e.target.value)} data-testid="cfg-short_pe_otm" /></Field>
            </>)}
            {config.short_method === "DELTA" && (<>
              <Field label="CE Target Delta"><input type="number" step="0.01" className={inputCls} value={config.short_ce_delta} onChange={(e) => num("short_ce_delta", e.target.value)} data-testid="cfg-short_ce_delta" /></Field>
              <Field label="PE Target Delta" hint="negative"><input type="number" step="0.01" className={inputCls} value={config.short_pe_delta} onChange={(e) => num("short_pe_delta", e.target.value)} data-testid="cfg-short_pe_delta" /></Field>
            </>)}
            {config.short_method === "PREMIUM" && (<>
              <Field label="CE Target Premium ₹"><input type="number" className={inputCls} value={config.short_ce_premium} onChange={(e) => num("short_ce_premium", e.target.value)} data-testid="cfg-short_ce_premium" /></Field>
              <Field label="PE Target Premium ₹"><input type="number" className={inputCls} value={config.short_pe_premium} onChange={(e) => num("short_pe_premium", e.target.value)} data-testid="cfg-short_pe_premium" /></Field>
            </>)}
            {config.short_method === "ATM" && <div className="col-span-2 text-[11px] font-mono text-slate-500 self-center">ATM CE &amp; PE selected nearest to the strategy center.</div>}
          </Section>

          <Section title="Hedge Legs" cols={3}>
            <Field label="Hedge Enabled">
              <button onClick={() => set("hedge_enabled", !config.hedge_enabled)} data-testid="cfg-hedge_enabled"
                className={`${inputCls} text-left ${config.hedge_enabled ? "!text-emerald-400" : "!text-slate-500"}`}>{config.hedge_enabled ? "ENABLED — defined risk" : "DISABLED — naked short"}</button>
            </Field>
            {config.hedge_enabled && <Field label="Hedge Method"><Sel k="hedge_method" opts={meta?.hedge_methods || ["STRIKE_DISTANCE","DELTA","PREMIUM"]} /></Field>}
            {config.hedge_enabled && config.hedge_method === "STRIKE_DISTANCE" && (<>
              <Field label="Long CE +steps"><input type="number" className={inputCls} value={config.hedge_ce_distance} onChange={(e) => num("hedge_ce_distance", e.target.value)} data-testid="cfg-hedge_ce_distance" /></Field>
              <Field label="Long PE -steps"><input type="number" className={inputCls} value={config.hedge_pe_distance} onChange={(e) => num("hedge_pe_distance", e.target.value)} data-testid="cfg-hedge_pe_distance" /></Field>
            </>)}
            {config.hedge_enabled && config.hedge_method === "DELTA" && (<>
              <Field label="Long CE Delta"><input type="number" step="0.01" className={inputCls} value={config.hedge_ce_delta} onChange={(e) => num("hedge_ce_delta", e.target.value)} data-testid="cfg-hedge_ce_delta" /></Field>
              <Field label="Long PE Delta"><input type="number" step="0.01" className={inputCls} value={config.hedge_pe_delta} onChange={(e) => num("hedge_pe_delta", e.target.value)} data-testid="cfg-hedge_pe_delta" /></Field>
            </>)}
            {config.hedge_enabled && config.hedge_method === "PREMIUM" && (<>
              <Field label="Long CE Premium ₹"><input type="number" className={inputCls} value={config.hedge_ce_premium} onChange={(e) => num("hedge_ce_premium", e.target.value)} data-testid="cfg-hedge_ce_premium" /></Field>
              <Field label="Long PE Premium ₹"><input type="number" className={inputCls} value={config.hedge_pe_premium} onChange={(e) => num("hedge_pe_premium", e.target.value)} data-testid="cfg-hedge_pe_premium" /></Field>
            </>)}
          </Section>

          <Section title="Execution Assumptions (Backtest / Paper)" cols={3}>
            <Field label="Slippage %"><input type="number" step="0.1" className={inputCls} value={config.slippage_pct} onChange={(e) => num("slippage_pct", e.target.value)} data-testid="cfg-slippage_pct" /></Field>
            <Field label="Brokerage / order ₹"><input type="number" className={inputCls} value={config.brokerage_per_order} onChange={(e) => num("brokerage_per_order", e.target.value)} data-testid="cfg-brokerage_per_order" /></Field>
            <Field label="Taxes %"><input type="number" step="0.01" className={inputCls} value={config.tax_pct} onChange={(e) => num("tax_pct", e.target.value)} data-testid="cfg-tax_pct" /></Field>
          </Section>
        </div>

        {/* Preview */}
        <div className="panel self-start" data-testid="basket-preview-panel">
          <div className="panel-header">Basket Preview</div>
          {!preview ? (
            <div className="p-4 text-xs font-mono text-slate-600">Click <b className="text-slate-400">Preview Basket</b> to resolve the four legs against the option chain.</div>
          ) : (
            <div className="p-3 space-y-3">
              <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                <div className="flex justify-between"><span className="text-slate-500">Spot</span><span>{fmt(preview.spot)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Center</span><span className="text-sky-400">{fmt(preview.center)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Upper</span><span className="text-amber-400">{fmt(preview.upper)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Lower</span><span className="text-purple-300">{fmt(preview.lower)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Expiry</span><span>{preview.expiry}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Qty</span><span className="text-emerald-400">{preview.total_qty}</span></div>
              </div>
              <table className="blotter">
                <thead><tr><th>Leg</th><th>Strike</th><th>Δ</th><th>Prem</th></tr></thead>
                <tbody>
                  {preview.legs.map((l, i) => (
                    <tr key={i}>
                      <td className={l.side === "SELL" ? "text-red-300" : "text-emerald-300"}>{l.side} {l.type}</td>
                      <td>{fmt(l.strike, 0)}</td><td>{fmt(l.delta)}</td><td>{fmt(l.premium)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="text-[11px] font-mono flex justify-between border-t border-[#243046] pt-2">
                <span className="text-slate-500">Net Premium</span><span className={preview.net_premium >= 0 ? "text-emerald-400" : "text-red-400"}>{money(preview.net_premium)}</span>
              </div>
              <div className="text-[9.5px] font-mono text-slate-600">{preview.note}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
