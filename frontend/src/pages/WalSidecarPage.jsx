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

const PRODUCT_AMOUNT = 499;

function SidecarStatusBadge({ status }) {
  if (status === "checking") {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-gray-600 bg-gray-500/10 px-3 py-1 text-xs text-gray-400">
        <Loader2 size={12} className="animate-spin" /> Checking sidecar…
      </span>
    );
  }
  if (status === "online") {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-green-500/40 bg-green-500/10 px-3 py-1 text-xs text-green-300">
        <Radio size={12} /> Sidecar online
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-500/10 px-3 py-1 text-xs text-red-300">
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
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-white">
              Local Sidecar WAL &amp; Self-Healing Agent
            </h1>
            <SidecarStatusBadge status={sidecarStatus} />
          </div>
          <p className="mt-1 text-sm text-gray-400">
            Approach B: a fully independent process (
            <code className="text-emerald-400">backend/sidecar/</code>) that durably witnesses
            Razorpay traffic on the wire, so it can reconstruct orders MongoDB never recorded at
            all -- not even <code className="text-gray-300">PENDING</code>.
          </p>
        </div>
      </div>

      {sidecarStatus === "offline" && (
        <div className="mb-6 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertOctagon size={16} />
          WAL sidecar unreachable. Run it separately:{" "}
          <code className="text-red-200">uvicorn sidecar.main:app --port 9000</code> from the{" "}
          <code className="text-red-200">backend/</code> directory.
        </div>
      )}

      <section className="mb-10 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-6">
        <div className="mb-4 flex items-center gap-2 text-emerald-400">
          <Skull size={20} />
          <span className="text-sm font-medium uppercase tracking-wide">
            Crash Simulator -- Zero DB Footprint
          </span>
        </div>
        <p className="mb-4 text-sm text-gray-400">
          This checkout calls a special endpoint that creates a real Razorpay order (relayed
          through the WAL sidecar) but <strong className="text-gray-200">never writes anything
          to MongoDB</strong> -- no order row, not even PENDING. After payment, no verification
          call happens either, modeling a server that crashed before it could process the
          response at all.
        </p>

        <label className="mb-4 block max-w-sm text-sm text-gray-400">
          Customer email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white outline-none focus:border-emerald-500"
          />
        </label>

        <button
          onClick={handleSimulateZeroDbCrash}
          disabled={crashing}
          className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 font-medium text-white transition hover:bg-emerald-500 disabled:opacity-60"
        >
          {crashing ? (
            <>
              <Loader2 size={18} className="animate-spin" /> Processing…
            </>
          ) : (
            <>
              <Skull size={18} /> Simulate Mid-Flight Server Crash &amp; Zero-DB Loss (₹
              {PRODUCT_AMOUNT})
            </>
          )}
        </button>

        {crashResult && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-3 text-sm text-emerald-200">
            <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
            {crashResult}
          </div>
        )}
        {crashError && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-3 text-sm text-red-300">
            <AlertOctagon size={18} className="mt-0.5 shrink-0" />
            {crashError}
          </div>
        )}
      </section>

      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-lg font-medium text-white">Self-Healing Control</h2>
        <button
          onClick={handleTriggerHeal}
          disabled={healing}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white transition hover:bg-indigo-500 disabled:opacity-60"
        >
          {healing ? (
            <>
              <Loader2 size={18} className="animate-spin" /> Healing…
            </>
          ) : (
            <>
              <DatabaseZap size={18} /> Trigger Local WAL Self-Heal
            </>
          )}
        </button>
      </div>

      {healResult && (
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">
          <CheckCircle2 size={16} />
          Heal run complete: {healResult.orphans_found} zero-footprint orphan(s) found,{" "}
          {healResult.healed_via_wal} reconstructed from WAL, {healResult.escalated} escalated.
        </div>
      )}
      {healError && (
        <div className="mb-6 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertOctagon size={16} />
          {healError}
        </div>
      )}

      <section className="mb-10 grid gap-6 md:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-medium text-white">
            Current Zero-Footprint Orphans ({orphans.length})
          </h2>
          {loadingData ? (
            <div className="py-6 text-center text-sm text-gray-500">Loading…</div>
          ) : orphans.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-white/5 py-6 text-center text-sm text-gray-500">
              None found. MongoDB has a record for every WAL-witnessed payment.
            </div>
          ) : (
            <div className="space-y-2">
              {orphans.map((o) => (
                <div
                  key={o.razorpay_payment_id || o.razorpay_order_id}
                  className="rounded-xl border border-orange-500/30 bg-orange-500/10 p-3 text-sm"
                >
                  <div className="font-mono text-xs text-orange-200">
                    {o.razorpay_order_id} / {o.razorpay_payment_id}
                  </div>
                  <div className="text-orange-300">
                    order_id: {o.order_id || "unknown"} · ₹{(o.amount_inr ?? 0).toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-medium text-white">
            <ScanLine size={18} /> Raw WAL Entries ({walEntries.length})
          </h2>
          <div className="max-h-80 space-y-2 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-3">
            {loadingData ? (
              <div className="py-6 text-center text-sm text-gray-500">Loading…</div>
            ) : walEntries.length === 0 ? (
              <div className="py-6 text-center text-sm text-gray-500">
                No traffic witnessed yet.
              </div>
            ) : (
              walEntries.map((e) => (
                <div key={e.id} className="rounded-lg bg-black/30 p-2 text-xs">
                  <span
                    className={`mr-2 rounded px-1.5 py-0.5 ${
                      e.direction === "request"
                        ? "bg-blue-500/20 text-blue-300"
                        : "bg-purple-500/20 text-purple-300"
                    }`}
                  >
                    {e.direction}
                  </span>
                  <span className="text-gray-400">{e.razorpay_path}</span>
                  <div className="mt-1 text-gray-500">
                    order_id={e.order_id || "-"} rzp_order={e.razorpay_order_id || "-"} rzp_payment=
                    {e.razorpay_payment_id || "-"}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-white">WAL Healing Audit Timeline</h2>
        <WalAuditTimeline auditLogs={auditLogs} loading={loadingData} />
      </section>
    </div>
  );
}
