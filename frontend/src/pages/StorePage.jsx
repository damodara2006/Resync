import { AlertTriangle, CheckCircle2, ShoppingBag, Skull } from "lucide-react";
import { useState } from "react";
import { createOrder, verifyPayment } from "../api/client";
import { loadRazorpayScript } from "../api/razorpay";

const PRODUCT = {
  name: "Resync Demo Hoodie",
  description: "Limited edition buildathon merch. Test-mode checkout only.",
  price: 499,
};

export default function StorePage() {
  const [email, setEmail] = useState("customer@example.com");
  const [simulateCrash, setSimulateCrash] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | processing | success | crashed | error
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
        theme: { color: "#6366f1" },
        handler: async (response) => {
          try {
            const result = await verifyPayment(
              {
                orderId: order.order_id,
                razorpayOrderId: response.razorpay_order_id,
                razorpayPaymentId: response.razorpay_payment_id,
                razorpaySignature: response.razorpay_signature,
              },
              simulateCrash
            );

            if (result.simulated_crash) {
              setStatus("crashed");
              setMessage(result.message);
            } else {
              setStatus("success");
              setMessage(result.message);
            }
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
    <div className="mx-auto max-w-md px-4 py-16">
      <div className="rounded-2xl border border-white/10 bg-white/5 p-6 shadow-xl backdrop-blur">
        <div className="mb-4 flex items-center gap-2 text-indigo-400">
          <ShoppingBag size={22} />
          <span className="text-sm font-medium uppercase tracking-wide">Resync Store</span>
        </div>

        <h1 className="text-2xl font-semibold text-white">{PRODUCT.name}</h1>
        <p className="mt-1 text-sm text-gray-400">{PRODUCT.description}</p>

        <div className="mt-6 flex items-baseline gap-1">
          <span className="text-3xl font-bold text-white">₹{PRODUCT.price}</span>
          <span className="text-sm text-gray-500">.00</span>
        </div>

        <label className="mt-6 block text-sm text-gray-400">
          Customer email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white outline-none focus:border-indigo-500"
          />
        </label>

        <div className="mt-4 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-3">
          <div className="flex items-center gap-2 text-sm text-red-300">
            <Skull size={16} />
            Simulate Server Crash / Webhook Drop
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={simulateCrash}
            onClick={() => setSimulateCrash((v) => !v)}
            className={`relative h-6 w-11 rounded-full transition-colors ${
              simulateCrash ? "bg-red-500" : "bg-gray-600"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                simulateCrash ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </button>
        </div>

        <button
          onClick={handleCheckout}
          disabled={status === "processing"}
          className="mt-6 w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {status === "processing" ? "Processing…" : `Pay ₹${PRODUCT.price} with Razorpay`}
        </button>

        {status === "success" && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-3 text-sm text-green-300">
            <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
            {message}
          </div>
        )}

        {status === "crashed" && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-orange-500/30 bg-orange-500/10 px-3 py-3 text-sm text-orange-300">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            {message}
          </div>
        )}

        {status === "error" && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-3 text-sm text-red-300">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            {message}
          </div>
        )}
      </div>
    </div>
  );
}
