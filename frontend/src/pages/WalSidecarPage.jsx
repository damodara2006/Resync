import {
  AlertOctagon,
  CheckCircle2,
  DatabaseZap,
  Loader2,
  Radio,
  ScanLine,
  Skull,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { createOrderCrashSimulation } from "../api/client";
import { loadRazorpayScript } from "../api/razorpay";
import {
  getWalAuditLogs,
  getWalEntries,
  getWalHealth,
  getWalOrphans,
  triggerWalHeal,
} from "../api/walClient";
import WalAuditTimeline from "../components/WalAuditTimeline";
import { PageContainer, PageHeader, Section } from "../components/PageShell";

const PRODUCT_AMOUNT = 499;

function SidecarStatusBadge({ status }) {
  if (status === "checking") {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-slate-300 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500">
        <Loader2 size={12} className="animate-spin" /> Checking sidecar…
      </span>
    );
  }
  if (status === "online") {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
        <Radio size={12} /> Sidecar online
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-red-300 bg-red-50 px-3 py-1 text-xs font-medium text-red-700">
      <AlertOctagon size={12} /> Sidecar unreachable
    </span>
  );
}

export default function WalSidecarPage() {
  const [sidecarStatus, setSidecarStatus] = useState("checking");
  const [email, setEmail] = useState("customer@example.com");
  const [crashing, setCrashing] = useState(false);
  const [crashResult, setCrashResult] = useState(null);
  const [crashError, setCrashError] = useState("");

  const [walEntries, setWalEntries] = useState([]);
  const [orphans, setOrphans] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [healing, setHealing] = useState(false);
  const [healResult, setHealResult] = useState(null);
  const [healError, setHealError] = useState("");

  const refreshSidecarData = useCallback(async () => {
    try {
      await getWalHealth();
      setSidecarStatus("online");
    } catch {
      setSidecarStatus("offline");
    }

    try {
      const [entries, orphanList, logs] = await Promise.all([
        getWalEntries(50),
        getWalOrphans(),
        getWalAuditLogs(),
      ]);
      setWalEntries(entries);
      setOrphans(orphanList);
      setAuditLogs(logs);
    } catch {
      // Sidecar likely offline -- leave existing data as-is.
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    refreshSidecarData();
  }, [refreshSidecarData]);

  async function handleSimulateZeroDbCrash() {
    setCrashing(true);
    setCrashResult(null);
    setCrashError("");

    try {
      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded) throw new Error("Failed to load Razorpay checkout script.");

      const order = await createOrderCrashSimulation({
        amount: PRODUCT_AMOUNT,
        customerEmail: email,
      });

      const options = {
        key: order.razorpay_key_id,
        amount: Math.round(order.amount * 100),
        currency: order.currency,
        name: "Resync Store (WAL Sidecar Demo)",
        description: "Mid-Flight Crash Simulation -- Zero DB Footprint",
        order_id: order.razorpay_order_id,
        prefill: { email },
        theme: { color: "#059669" },
        handler: () => {
          // Deliberately NO backend call here at all -- this models the
          // server crashing before it could process the payment result in
          // any way. MongoDB will have zero record of this order; only the
          // WAL sidecar (which already relayed the create-order call) has
          // a trace.
          setCrashResult(
            `Payment completed on Razorpay for order ${order.razorpay_order_id}, ` +
              "but this backend never processed the result -- simulating a full " +
              "mid-flight crash. MongoDB has ZERO record of this order. Only the " +
              "WAL sidecar's independent log has a trace. Refresh the WAL data below " +
              "to see it, then trigger self-heal."
          );
          refreshSidecarData();
        },
        modal: {
          ondismiss: () => setCrashing(false),
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      setCrashError(
        err?.response?.data?.detail || err.message || "Crash simulation checkout failed."
      );
    } finally {
      setCrashing(false);
    }
  }

  async function handleTriggerHeal() {
    setHealing(true);
    setHealResult(null);
    setHealError("");
    try {
      const result = await triggerWalHeal();
      setHealResult(result);
      await refreshSidecarData();
    } catch (err) {
      setHealError(err?.response?.data?.detail || "WAL self-heal run failed.");
    } finally {
      setHealing(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Local WAL & Self-Healing Agent"
        status={<SidecarStatusBadge status={sidecarStatus} />}
        description={
          <>
            A local Write-Ahead Log durably witnesses Razorpay traffic on the wire, so it can
            reconstruct orders MongoDB never recorded at all — not even{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-slate-700">PENDING</code>.
          </>
        }
        actions={
          <button
            onClick={handleTriggerHeal}
            disabled={healing}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {healing ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Healing…
              </>
            ) : (
              <>
                <DatabaseZap size={16} /> Trigger self-heal
              </>
            )}
          </button>
        }
      />

      <PageContainer className="space-y-8">
        {sidecarStatus === "offline" && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertOctagon size={16} className="shrink-0" />
            WAL sidecar unreachable. Run it separately:{" "}
            <code className="rounded bg-red-100 px-1 py-0.5 text-red-800">
              uvicorn sidecar.main:app --port 9000
            </code>{" "}
            from the <code className="rounded bg-red-100 px-1 py-0.5 text-red-800">backend/</code>{" "}
            directory.
          </div>
        )}

        {(healResult || healError) && (
          <div>
            {healResult && (
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
                <CheckCircle2 size={16} className="shrink-0" />
                Heal run complete: {healResult.orphans_found} zero-footprint orphan(s) found,{" "}
                {healResult.healed_via_wal} reconstructed from WAL, {healResult.escalated}{" "}
                escalated.
              </div>
            )}
            {healError && (
              <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                <AlertOctagon size={16} className="shrink-0" />
                {healError}
              </div>
            )}
          </div>
        )}

        <Section
          tone="accent"
          icon={Skull}
          title="Crash simulator — zero DB footprint"
          description="Creates a real Razorpay order relayed through the WAL sidecar, then deliberately skips every database write to model a server that crashes mid-flight."
        >
          <p className="mb-5 max-w-3xl text-sm leading-relaxed text-slate-600">
            After payment, no verification call happens either.{" "}
            <strong className="text-slate-900">MongoDB ends up with zero record</strong> of the
            order — not even a PENDING row. Only the WAL sidecar's independent log has a trace of
            it.
          </p>

          <div className="flex flex-wrap items-end gap-4">
            <label className="block w-full max-w-xs text-sm font-medium text-slate-700">
              Customer email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </label>

            <button
              onClick={handleSimulateZeroDbCrash}
              disabled={crashing}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {crashing ? (
                <>
                  <Loader2 size={18} className="animate-spin" /> Processing…
                </>
              ) : (
                <>
                  <Skull size={18} /> Simulate crash (₹{PRODUCT_AMOUNT})
                </>
              )}
            </button>
          </div>

          {crashResult && (
            <div className="mt-5 flex items-start gap-2 rounded-lg border border-emerald-200 bg-white px-3 py-3 text-sm text-emerald-800">
              <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
              {crashResult}
            </div>
          )}
          {crashError && (
            <div className="mt-5 flex items-start gap-2 rounded-lg border border-red-200 bg-white px-3 py-3 text-sm text-red-700">
              <AlertOctagon size={18} className="mt-0.5 shrink-0" />
              {crashError}
            </div>
          )}
        </Section>

        <div className="grid gap-6 md:grid-cols-2">
          <Section title={`Zero-footprint orphans (${orphans.length})`}>
            {loadingData ? (
              <div className="py-6 text-center text-sm text-slate-500">Loading…</div>
            ) : orphans.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 py-6 text-center text-sm text-slate-500">
                None found. MongoDB has a record for every WAL-witnessed payment.
              </div>
            ) : (
              <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                {orphans.map((o) => (
                  <div
                    key={o.razorpay_payment_id || o.razorpay_order_id}
                    className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm"
                  >
                    <div className="font-mono text-xs text-orange-800">
                      {o.razorpay_order_id} / {o.razorpay_payment_id}
                    </div>
                    <div className="mt-0.5 text-orange-700">
                      order_id: {o.order_id || "unknown"} · ₹{(o.amount_inr ?? 0).toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section icon={ScanLine} title={`Raw WAL entries (${walEntries.length})`}>
            <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
              {loadingData ? (
                <div className="py-6 text-center text-sm text-slate-500">Loading…</div>
              ) : walEntries.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 py-6 text-center text-sm text-slate-500">
                  No traffic witnessed yet.
                </div>
              ) : (
                walEntries.map((e) => (
                  <div key={e.id} className="rounded-lg bg-slate-50 p-2.5 text-xs">
                    <span
                      className={`mr-2 rounded px-1.5 py-0.5 font-medium ${
                        e.direction === "request"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-purple-100 text-purple-700"
                      }`}
                    >
                      {e.direction}
                    </span>
                    <span className="text-slate-500">{e.razorpay_path}</span>
                    <div className="mt-1 text-slate-400">
                      order_id={e.order_id || "-"} rzp_order={e.razorpay_order_id || "-"}{" "}
                      rzp_payment={e.razorpay_payment_id || "-"}
                    </div>
                  </div>
                ))
              )}
            </div>
          </Section>
        </div>

        <Section title="WAL healing audit timeline">
          <WalAuditTimeline auditLogs={auditLogs} loading={loadingData} />
        </Section>
      </PageContainer>
    </>
  );
}
