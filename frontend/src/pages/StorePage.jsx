import { AlertTriangle, CheckCircle2, ShieldCheck, ShoppingBag, Sparkles } from "lucide-react";
import { useState } from "react";
import { createOrder, verifyPayment } from "../api/client";
import { loadRazorpayScript } from "../api/razorpay";
import { PageContainer, PageHeader } from "../components/PageShell";

const PRODUCT = {
  name: "Resync Demo Hoodie",
  description: "Limited edition buildathon merch. Test-mode checkout only.",
  price: 499,
};

const FEATURES = [
  { text: "Secured with Razorpay test-mode payments" },
  { text: "Order reconciliation verified on every purchase" },
  { text: "Every transaction auditable end to end" },
];

export default function StorePage() {
  const [email, setEmail] = useState("customer@example.com");
  const [status, setStatus] = useState("idle"); // idle | processing | success | error
  const [message, setMessage] = useState("");

  async function handleCheckout() {
    setStatus("processing");
    setMessage("");

    try {
      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded) {
        throw new Error("Failed to load Razorpay checkout script.");
      }

      const order = await createOrder({ amount: PRODUCT.price, customerEmail: email });

      const options = {
        key: order.razorpay_key_id,
        amount: Math.round(order.amount * 100),
        currency: order.currency,
        name: "Resync Store",
        description: PRODUCT.name,
        order_id: order.razorpay_order_id,
        prefill: { email },
        theme: { color: "#4f46e5" },
        handler: async (response) => {
          try {
            const result = await verifyPayment({
              orderId: order.order_id,
              razorpayOrderId: response.razorpay_order_id,
              razorpayPaymentId: response.razorpay_payment_id,
              razorpaySignature: response.razorpay_signature,
            });

            setStatus("success");
            setMessage(result.message);
          } catch (err) {
            setStatus("error");
            setMessage(err?.response?.data?.detail || "Payment verification failed.");
          }
        },
        modal: {
          ondismiss: () => setStatus("idle"),
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      setStatus("error");
      setMessage(err?.response?.data?.detail || err.message || "Checkout failed.");
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Demo checkout"
        title="Resync Store"
        description="A minimal storefront used to demonstrate reliable payment capture and reconciliation. Complete a test purchase below to see it end to end."
      />

      <PageContainer>
        <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:items-start">
          <div className="lg:pt-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
              <Sparkles size={13} />
              Featured item
            </span>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
              {PRODUCT.name}
            </h2>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-slate-600">
              {PRODUCT.description}
            </p>

            <ul className="mt-8 space-y-3">
              {FEATURES.map((f) => (
                <li key={f.text} className="flex items-center gap-2.5 text-sm text-slate-600">
                  <ShieldCheck size={16} className="shrink-0 text-indigo-600" />
                  {f.text}
                </li>
              ))}
            </ul>

            <div className="mt-8 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
              Curious how Resync recovers payments after a mid-flight crash? Explore the{" "}
              <a href="/wal-sidecar" className="font-medium text-indigo-600 hover:text-indigo-700">
                WAL Sidecar
              </a>{" "}
              demo.
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-200/60 sm:p-7">
            <div className="mb-5 flex items-center gap-2 text-indigo-600">
              <ShoppingBag size={18} />
              <span className="text-xs font-semibold uppercase tracking-wide">Order summary</span>
            </div>

            <div className="flex items-baseline justify-between border-b border-slate-100 pb-5">
              <span className="text-sm text-slate-600">{PRODUCT.name}</span>
              <span className="text-2xl font-semibold text-slate-900">
                ₹{PRODUCT.price}
                <span className="text-sm font-normal text-slate-400">.00</span>
              </span>
            </div>

            <label className="mt-5 block text-sm font-medium text-slate-700">
              Customer email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              />
            </label>

            <button
              onClick={handleCheckout}
              disabled={status === "processing"}
              className="mt-6 w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {status === "processing" ? "Processing…" : `Pay ₹${PRODUCT.price} with Razorpay`}
            </button>

            {status === "success" && (
              <div className="mt-4 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
                <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
                {message}
              </div>
            )}

            {status === "error" && (
              <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">
                <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                {message}
              </div>
            )}

            <p className="mt-5 text-center text-xs text-slate-400">
              Test mode only — no real charges are made.
            </p>
          </div>
        </div>
      </PageContainer>
    </>
  );
}
