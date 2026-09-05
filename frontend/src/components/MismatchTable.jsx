import { AlertCircle } from "lucide-react";

const statusColors = {
  PENDING: "bg-yellow-500/15 text-yellow-300 border-yellow-500/30",
  DESYNCHRONIZED: "bg-red-500/15 text-red-300 border-red-500/30",
  FULFILLED: "bg-green-500/15 text-green-300 border-green-500/30",
  REFUNDED: "bg-blue-500/15 text-blue-300 border-blue-500/30",
};

function StatusPill({ status }) {
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${
        statusColors[status] || "bg-gray-500/15 text-gray-300 border-gray-500/30"
      }`}
    >
      {status}
    </span>
  );
}

export default function MismatchTable({ desyncs, loading }) {
  if (loading) {
    return <div className="py-10 text-center text-sm text-gray-500">Loading mismatches…</div>;
  }

  if (desyncs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-gray-500">
        <AlertCircle size={24} className="text-gray-600" />
        No desynchronized orders. Everything is reconciled.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/10">
      <table className="w-full text-left text-sm">
        <thead className="bg-white/5 text-gray-400">
          <tr>
            <th className="px-4 py-3 font-medium">Order ID</th>
            <th className="px-4 py-3 font-medium">Customer</th>
            <th className="px-4 py-3 font-medium">Amount</th>
            <th className="px-4 py-3 font-medium">Razorpay Status</th>
            <th className="px-4 py-3 font-medium">DB Status</th>
            <th className="px-4 py-3 font-medium">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {desyncs.map((row) => (
            <tr key={row.order_id} className="hover:bg-white/5">
              <td className="px-4 py-3 font-mono text-xs text-gray-300">{row.order_id}</td>
              <td className="px-4 py-3 text-gray-300">{row.customer_email}</td>
              <td className="px-4 py-3 text-gray-300">₹{row.amount.toFixed(2)}</td>
              <td className="px-4 py-3">
                <StatusPill status={row.razorpay_status === "captured" ? "FULFILLED" : "PENDING"} />
                <span className="ml-1 text-xs text-gray-500">({row.razorpay_status})</span>
              </td>
              <td className="px-4 py-3">
                <StatusPill status={row.db_status} />
              </td>
              <td className="px-4 py-3 text-xs text-gray-500">
                {new Date(row.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
