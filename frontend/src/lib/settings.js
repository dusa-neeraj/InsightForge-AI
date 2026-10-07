const KEY = "ada.currency";

export const CURRENCIES = [
  { symbol: "", label: "No symbol" },
  { symbol: "₹", label: "₹ Rupee" },
  { symbol: "$", label: "$ Dollar" },
  { symbol: "€", label: "€ Euro" },
  { symbol: "£", label: "£ Pound" },
];

export function getCurrency() {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function setCurrency(symbol) {
  try {
    localStorage.setItem(KEY, symbol);
  } catch {
    // storage is blocked, the choice just won't be remembered
  }
}