const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(data, status) {
  if (data?.error) return data.error;
  if (Array.isArray(data?.detail)) return data.detail.map((d) => d.msg).join(". ");
  return `Request failed (${status}).`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, options);
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    // the response had no JSON body
  }
  if (!response.ok) throw new ApiError(errorMessage(data, response.status), response.status);
  return data;
}

const post = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// XMLHttpRequest is used here (not fetch) because it reports upload progress.
export function uploadDataset(file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE_URL}/upload`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // not JSON
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(errorMessage(data, xhr.status), xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Cannot reach the server. Is the backend running?", 0));
    xhr.send(form);
  });
}

export const getHealth = () => request("/health");
export const getProfile = (id, version = "clean") => request(`/datasets/${id}/profile?version=${version}`);
export const getPreview = (id, rows = 20) => request(`/datasets/${id}/preview?rows=${rows}`);
export const getQuality = (id) => request(`/datasets/${id}/quality`);
export const getEda = (id) => request(`/datasets/${id}/eda`);
export const getCharts = (id) => request(`/datasets/${id}/charts`);
export const getKpis = (id) => request(`/datasets/${id}/kpis`);
export const getInsights = (id, refresh = false) => request(`/datasets/${id}/insights?refresh=${refresh}`);
export const sendChat = (id, question, sessionId) =>
  post(`/datasets/${id}/chat`, { question, session_id: sessionId || null });
export const getChatHistory = (id, sessionId) => request(`/datasets/${id}/chat/${sessionId}`);
export const runSql = (id, body) => post(`/datasets/${id}/sql`, body);
export const getSqlSchema = (id) => request(`/datasets/${id}/sql/schema`);