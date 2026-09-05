import {
  AlertOctagon,
  CheckCircle2,
  Loader2,
  ScanLine,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getAuditLogs, getDesyncs, getMetrics, runReconciliation } from "../api/client";
import AuditTimeline from "../components/AuditTimeline";
import MetricCard from "../components/MetricCard";
import MismatchTable from "../components/MismatchTable";

export default function AdminPage() {
  const [metrics, setMetrics] = useState(null);
  const [desyncs, setDesyncs] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    setError("");
    try {
      const [metricsData, desyncsData, auditData] = await Promise.all([
        getMetrics(),
        getDesyncs(),
        getAuditLogs(),
      ]);
      setMetrics(metricsData);
      setDesyncs(desyncsData);
      setAuditLogs(auditData);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleRunAgent() {
    setRunning(true);
    setRunResult(null);
    setError("");
    try {
      const result = await runReconciliation();
      setRunResult(result);
      await loadAll();
    } catch (err) {
      setError(err?.response?.data?.detail || "Reconciliation run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Reconciliation Dashboard</h1>
          <p className="text-sm text-gray-400">
            Live view of phantom transactions and the AI agent's decision trail.
          </p>
        </div>

        <button
          onClick={handleRunAgent}
          disabled={running}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white transition hover:bg-indigo-500 disabled:opacity-60"
        >
          {running ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              Running Agent…
            </>
          ) : (
            <>
              <ScanLine size={18} />
              Run AI Reconciliation Agent
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertOctagon size={16} />
          {error}
        </div>
      )}

      {runResult && (
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">
          <CheckCircle2 size={16} />
          Scan complete: {runResult.scanned_payments} payment(s) scanned,{" "}
          {runResult.anomalies_found} anomaly(ies) found, {runResult.auto_healed} auto-healed,{" "}
          {runResult.escalated} escalated.
        </div>
      )}

      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard label="Total Scanned" value={metrics?.total_scanned ?? "—"} icon={ScanLine} />
        <MetricCard
          label="Active Desyncs"
          value={metrics?.active_desyncs ?? "—"}
          icon={AlertOctagon}
          tone="warning"
        />
        <MetricCard
          label="Auto-Healed"
          value={metrics?.auto_healed ?? "—"}
          icon={CheckCircle2}
          tone="success"
        />
        <MetricCard
          label="Escalated"
          value={metrics?.escalated ?? "—"}
          icon={Sparkles}
          tone="danger"
        />
      </div>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-medium text-white">Live Mismatch Table</h2>
        <MismatchTable desyncs={desyncs} loading={loading} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-white">Audit Timeline</h2>
        <AuditTimeline auditLogs={auditLogs} loading={loading} />
      </section>
    </div>
  );
}
