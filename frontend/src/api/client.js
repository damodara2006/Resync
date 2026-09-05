import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

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

export async function verifyPayment(
  { orderId, razorpayOrderId, razorpayPaymentId, razorpaySignature },
  simulateCrash = false
) {
  const { data } = await apiClient.post(
    "/api/checkout/verify",
    {
      order_id: orderId,
      razorpay_order_id: razorpayOrderId,
      razorpay_payment_id: razorpayPaymentId,
      razorpay_signature: razorpaySignature,
    },
    { params: { simulate_crash: simulateCrash } }
  );
  return data;
}

export async function runReconciliation() {
  const { data } = await apiClient.post("/api/agent/run-reconciliation");
  return data;
}

export async function getDesyncs() {
  const { data } = await apiClient.get("/api/admin/desyncs");
  return data;
}

export async function getAuditLogs() {
  const { data } = await apiClient.get("/api/admin/audit-logs");
  return data;
}

export async function getMetrics() {
  const { data } = await apiClient.get("/api/admin/metrics");
  return data;
}
