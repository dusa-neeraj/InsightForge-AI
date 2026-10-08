import { formatNumber } from "../lib/format.js";

// IDs, years and codes should not get thousands separators
const RAW_NAME = /(^|_)(id|year|zip|pin|code|phone)$/i;

function cellText(value, column) {
  if (value === null || value === undefined) return <span className="text-slate-300">—</span>;
  if (typeof value === "number") return RAW_NAME.test(column) ? String(value) : formatNumber(value, 4);
  return String(value);
}

export default function DataTable({ columns, rows, maxRows = 50, height = "max-h-80" }) {
  const shown = rows.slice(0, maxRows);
  return (
    <div>
      <div className={`overflow-auto ${height}`}>
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {columns.map((name, i) => (
                <th key={`${name}-${i}`} className="whitespace-nowrap px-3 py-2 font-medium">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="whitespace-nowrap px-3 py-2 text-slate-700">
                    {cellText(cell, columns[j])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown.length && (
        <p className="border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
          Showing {shown.length} of {rows.length} rows
        </p>
      )}
    </div>
  );
}