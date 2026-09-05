const RAZORPAY_SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

let scriptPromise = null;

export function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve(true);
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = RAZORPAY_SCRIPT_SRC;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });

  return scriptPromise;
}
