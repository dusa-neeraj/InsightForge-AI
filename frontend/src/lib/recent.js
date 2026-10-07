const KEY = "ada.recentDatasets";
const MAX = 5;

export function getRecent() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

function save(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // storage is full or blocked, the app still works without it
  }
}

export function addRecent(entry) {
  const list = [entry, ...getRecent().filter((item) => item.id !== entry.id)].slice(0, MAX);
  save(list);
  return list;
}

export function removeRecent(id) {
  const list = getRecent().filter((item) => item.id !== id);
  save(list);
  return list;
}

export function recentName(id) {
  return getRecent().find((item) => item.id === id)?.filename;
}