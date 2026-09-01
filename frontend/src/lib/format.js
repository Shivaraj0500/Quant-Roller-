export const fmt = (n, d = 2) =>
  (n === null || n === undefined || isNaN(n)) ? "—"
    : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

export const fmt0 = (n) => fmt(n, 0);

export const money = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const s = n < 0 ? "-" : "";
  return `${s}₹${fmt(Math.abs(n), 0)}`;
};

export const pnlColor = (n) =>
  n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-slate-400";

export const hhmm = (iso) => {
  if (!iso) return "—";
  try { return iso.slice(11, 16); } catch { return "—"; }
};

export const STATE_STYLE = {
  WAITING: "bg-slate-800 text-slate-400 border-slate-600",
  INITIAL_QUALIFICATION: "bg-blue-950 text-blue-400 border-blue-600",
  ENTERING: "bg-blue-950 text-blue-300 border-blue-500",
  ACTIVE_BASKET: "bg-emerald-950 text-emerald-400 border-emerald-600",
  ROLL_UP: "bg-amber-950 text-amber-300 border-amber-600",
  ROLL_DOWN: "bg-purple-950 text-purple-200 border-purple-600",
  EXITING: "bg-rose-950 text-rose-300 border-rose-600",
  COMPLETED: "bg-green-950 text-green-300 border-green-600",
  EXECUTION_ATTENTION: "bg-yellow-900 text-yellow-300 border-yellow-500",
  ERROR: "bg-red-950 text-red-400 border-red-600",
};

export const MODE_STYLE = {
  BACKTEST: "bg-indigo-950/80 border-indigo-600/60 text-indigo-300",
  PAPER: "bg-sky-950/80 border-sky-600/60 text-sky-300",
  LIVE: "bg-red-950/80 border-red-600 text-red-300 animate-pulse",
};
