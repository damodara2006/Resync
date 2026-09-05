import axios from "axios";

// The WAL Sidecar is the only backend process -- it hosts both the
// storefront checkout endpoints and its own proxy/healing endpoints.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:9000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export async function createOrder({ amount, customerEmail }) {
  const { data } = await apiClient.post("/api/checkout/create-order", {
    amount,
    customer_email: customerEmail,
  });
  return data;
}

export async function createOrderCrashSimulation({ amount, customerEmail }) {
  const { data } = await apiClient.post("/api/checkout/create-order-crash-simulation", {
    amount,
    customer_email: customerEmail,
  });
  return data;
}

export async function verifyPayment({
  orderId,
  razorpayOrderId,
  razorpayPaymentId,
  razorpaySignature,
}) {
  const { data } = await apiClient.post("/api/checkout/verify", {
    order_id: orderId,
    razorpay_order_id: razorpayOrderId,
    razorpay_payment_id: razorpayPaymentId,
    razorpay_signature: razorpaySignature,
  });
  return data;
}
