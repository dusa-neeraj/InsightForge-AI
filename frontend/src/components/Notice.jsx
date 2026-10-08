const TONES = {
  red: "border-red-200 bg-red-50 text-red-800",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  slate: "border-slate-200 bg-slate-50 text-slate-700",
  indigo: "border-indigo-200 bg-indigo-50 text-indigo-800",
};

export default function Notice({ tone = "slate", title, children }) {
  return (
    <div className={`rounded-xl border p-4 text-sm ${TONES[tone]}`} role={tone === "red" ? "alert" : "status"}>
      {title && <p className="font-medium">{title}</p>}
      <div className={title ? "mt-1" : ""}>{children}</div>
    </div>
  );
}