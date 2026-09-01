import { useEffect, useRef, useState } from "react";

// Lightweight SVG candlestick chart with ATR corridor + strategy event markers.
export default function CandleChart({ candles = [], center, upper, lower, events = [], spot }) {
  const ref = useRef(null);
  const [w, setW] = useState(900);
  const H = 100;

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setW(Math.max(320, e.contentRect.width));
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const height = 460;
  const padL = 8, padR = 66, padT = 14, padB = 22;
  const plotW = w - padL - padR;
  const plotH = height - padT - padB;

  if (!candles.length) {
    return (
      <div ref={ref} className="flex-1 flex items-center justify-center text-slate-600 text-sm font-mono">
        NO MARKET DATA — START A PAPER / LIVE SESSION OR RUN A BACKTEST
      </div>
    );
  }

  const highs = candles.map((c) => c.h);
  const lows = candles.map((c) => c.l);
  let max = Math.max(...highs, upper || -Infinity);
  let min = Math.min(...lows, lower || Infinity);
  const span = (max - min) || 1;
  max += span * 0.04; min -= span * 0.04;
  const range = max - min;

  const y = (p) => padT + (1 - (p - min) / range) * plotH;
  const n = candles.length;
  const cw = plotW / n;
  const bodyW = Math.max(1.5, Math.min(cw * 0.62, 12));
  const x = (i) => padL + i * cw + cw / 2;

  const tsIndex = {};
  candles.forEach((c, i) => { tsIndex[c.ts] = i; });

  const gridLines = 5;
  const grid = Array.from({ length: gridLines + 1 }, (_, i) => min + (range * i) / gridLines);

  const markerColor = { "INITIAL ENTRY": "#3B82F6", ROLL_UP: "#F59E0B", ROLL_DOWN: "#A855F7", EXIT: "#F43F5E", EMERGENCY: "#EF4444" };

  return (
    <div ref={ref} className="flex-1 min-h-0 w-full" data-testid="strategy-candlestick-chart">
      <svg width={w} height={height} className="block">
        {/* grid */}
        {grid.map((p, i) => (
          <g key={i}>
            <line x1={padL} y1={y(p)} x2={w - padR} y2={y(p)} stroke="#1a2234" strokeWidth="1" />
            <text x={w - padR + 4} y={y(p) + 3} fill="#475569" fontSize="9" fontFamily="JetBrains Mono">{p.toFixed(0)}</text>
          </g>
        ))}

        {/* ATR corridor */}
        {upper ? <line x1={padL} y1={y(upper)} x2={w - padR} y2={y(upper)} stroke="#F59E0B" strokeWidth="1" strokeDasharray="5 3" opacity="0.85" /> : null}
        {lower ? <line x1={padL} y1={y(lower)} x2={w - padR} y2={y(lower)} stroke="#A855F7" strokeWidth="1" strokeDasharray="5 3" opacity="0.85" /> : null}
        {center ? <line x1={padL} y1={y(center)} x2={w - padR} y2={y(center)} stroke="#38BDF8" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" /> : null}
        {upper && lower ? <rect x={padL} y={y(upper)} width={plotW} height={Math.max(0, y(lower) - y(upper))} fill="#38BDF8" opacity="0.04" /> : null}

        {/* candles */}
        {candles.map((c, i) => {
          const up = c.c >= c.o;
          const col = up ? "#10B981" : "#EF4444";
          const yo = y(c.o), yc = y(c.c);
          const top = Math.min(yo, yc);
          const h = Math.max(1, Math.abs(yc - yo));
          return (
            <g key={i}>
              <line x1={x(i)} y1={y(c.h)} x2={x(i)} y2={y(c.l)} stroke={col} strokeWidth="1" />
              <rect x={x(i) - bodyW / 2} y={top} width={bodyW} height={h} fill={col} />
            </g>
          );
        })}

        {/* current price line + tag */}
        {spot ? (
          <g>
            <line x1={padL} y1={y(spot)} x2={w - padR} y2={y(spot)} stroke="#E2E8F0" strokeWidth="1" strokeDasharray="1 2" opacity="0.5" />
            <rect x={w - padR} y={y(spot) - 8} width={padR} height={16} fill="#1E293B" stroke="#334155" />
            <text x={w - padR + 4} y={y(spot) + 3} fill="#F1F5F9" fontSize="9.5" fontFamily="JetBrains Mono" fontWeight="600">{spot.toFixed(1)}</text>
          </g>
        ) : null}

        {/* event markers */}
        {events.map((ev, i) => {
          const idx = tsIndex[ev.ts];
          if (idx === undefined) return null;
          const c = candles[idx];
          const col = markerColor[ev.type] || "#94A3B8";
          const yy = ev.type === "ROLL_DOWN" || ev.type === "EXIT" ? y(c.l) + 12 : y(c.h) - 12;
          return (
            <g key={i}>
              <circle cx={x(idx)} cy={yy} r="3.5" fill={col} stroke="#0B0E14" strokeWidth="1" />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
