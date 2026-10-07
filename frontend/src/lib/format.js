const numberFormat = (digits) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits });

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) return "—";
  return numberFormat(digits).format(value);
}

export function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return `${formatNumber(value, 1)}%`;
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Turns a KPI card from the API into display text. The backend can't know the currency symbol.
export function kpiValue(card, currency = "") {
  const value = card.value;
  if (typeof value !== "number") return card.display;
  if (card.format === "money") return `${currency}${formatNumber(value)}`;
  if (card.format === "count" || card.format === "number") return formatNumber(value);
  return card.display;
}