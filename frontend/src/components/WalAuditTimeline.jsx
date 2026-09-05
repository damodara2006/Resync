import { ChevronDown, HardDriveDownload, ShieldAlert, Sparkles } from "lucide-react";
import { useState } from "react";

const actionMeta = {
  AUTO_FULFILL_VIA_WAL: {
    label: "Reconstructed from Local WAL",
    icon: HardDriveDownload,
    classes: "text-emerald-700 border-emerald-200 bg-emerald-50",
  },
  HUMAN_ESCALATION: {
    label: "Escalated to Human",
    icon: ShieldAlert,
    classes: "text-orange-700 border-orange-200 bg-orange-50",
  },
};

function WalAuditEntry({ entry }) {
  const [expanded, setExpanded] = useState(false);
  const meta = actionMeta[entry.action_taken] || actionMeta.HUMAN_ESCALATION;
  const Icon = meta.icon;
  const steps = entry.reasoning.split("\n").filter(Boolean);

  return (
    <div className={`rounded-xl border ${meta.classes} p-4`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <div className="flex items-center gap-3">
          <Icon size={20} className="shrink-0" />
          <div>
            <div className="font-medium text-slate-900">{meta.label}</div>
            <div className="text-xs text-slate-500">
              Order {entry.order_id} · Payment {entry.razorpay_payment_id} ·{" "}
              {new Date(entry.timestamp).toLocaleString()}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-xs text-slate-500">
            <Sparkles size={14} />
            confidence {(entry.confidence_score * 100).toFixed(0)}%
          </div>
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
              entry.safety_gate_passed
                ? "border-emerald-300 bg-emerald-100 text-emerald-700"
                : "border-red-300 bg-red-100 text-red-700"
            }`}
          >
            gate {entry.safety_gate_passed ? "passed" : "failed"}
          </span>
          <ChevronDown
            size={16}
            className={`text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {expanded && (
        <ol className="mt-4 space-y-2 border-l border-slate-300/70 pl-4">
          {steps.map((step, i) => (
            <li key={i} className="relative text-sm text-slate-600">
              <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-current opacity-60" />
              {step}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function WalAuditTimeline({ auditLogs, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white py-10 text-center text-sm text-slate-500">
        Loading WAL audit trail…
      </div>
    );
  }

  if (auditLogs.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white py-10 text-center text-sm text-slate-500">
        No WAL healing entries yet. Simulate a zero-DB crash, then trigger self-heal.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {auditLogs.map((entry) => (
        <WalAuditEntry key={entry.audit_id} entry={entry} />
      ))}
    </div>
  );
}
