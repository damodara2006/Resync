import axios from "axios";

// Approach B is a fully independent process from the main Resync backend --
// see backend/sidecar/. This client talks directly to that sidecar (default
// port 9000), never through the main backend's API base URL.
const WAL_SIDECAR_URL = import.meta.env.VITE_WAL_SIDECAR_URL || "http://localhost:9000";

export const walClient = axios.create({
  baseURL: WAL_SIDECAR_URL,
  headers: { "Content-Type": "application/json" },
});

export async function getWalHealth() {
  const { data } = await walClient.get("/health");
  return data;
}

export async function getWalEntries(limit = 200) {
  const { data } = await walClient.get("/wal/entries", { params: { limit } });
  return data;
}

export async function getWalOrphans() {
  const { data } = await walClient.get("/wal/orphans");
  return data;
}

export async function triggerWalHeal() {
  const { data } = await walClient.post("/wal/heal");
  return data;
}

export async function getWalAuditLogs(limit = 200) {
  const { data } = await walClient.get("/wal/audit-logs", { params: { limit } });
  return data;
}
