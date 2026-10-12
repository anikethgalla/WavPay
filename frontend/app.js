/**
 * PalmPay Frontend Application Controller
 * Handles real-time biometric scan polling, live camera viewfinder feed, Razorpay Checkout SDK, and Enrollment
 */

let currentAuthenticatedUser = null;
let lastSeenEventId = null;
let pollTimer = null;
let viewfinderTimer = null;
let isPaymentInProgress = false;
let isEnrollingActive = false;
let currentCheckoutMode = "auto"; // "auto" or "modal"
let autoDebitTimer = null;

// -------------------------------------------------------------
// Initialization
// -------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  switchTab("terminal");
  startPolling();
  startViewfinderFeed();
});

function setCheckoutMode(mode) {
  currentCheckoutMode = mode;
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
  const activeBtn = document.getElementById(mode === "auto" ? "modeAuto" : "modeModal");
  if (activeBtn) activeBtn.classList.add("active");

  const banner = document.getElementById("autoDebitBanner");
  if (banner) {
    if (mode === "auto") banner.classList.remove("hidden");
    else banner.classList.add("hidden");
  }

  // If user switches away from auto while verified screen is visible, cancel timer
  if (mode !== "auto" && autoDebitTimer) {
    clearTimeout(autoDebitTimer);
    autoDebitTimer = null;
  }
}

function switchTab(tabName) {
  const terminalBtn = document.getElementById("tabTerminal");
  const enrollBtn = document.getElementById("tabEnroll");
  const terminalView = document.getElementById("viewTerminal");
  const enrollView = document.getElementById("viewEnroll");

  if (tabName === "terminal") {
    if (terminalBtn) terminalBtn.classList.add("active");
    if (enrollBtn) enrollBtn.classList.remove("active");
    if (terminalView) {
      terminalView.classList.add("active");
      terminalView.classList.remove("hidden");
      terminalView.style.display = "block";
    }
    if (enrollView) {
      enrollView.classList.remove("active");
      enrollView.classList.add("hidden");
      enrollView.style.display = "none";
    }
  } else {
    if (enrollBtn) enrollBtn.classList.add("active");
    if (terminalBtn) terminalBtn.classList.remove("active");
    if (enrollView) {
      enrollView.classList.add("active");
      enrollView.classList.remove("hidden");
      enrollView.style.display = "block";
    }
    if (terminalView) {
      terminalView.classList.remove("active");
      terminalView.classList.add("hidden");
      terminalView.style.display = "none";
    }
  }
}

// -------------------------------------------------------------
// Live Camera Viewfinder Feed Auto-Refresh
// -------------------------------------------------------------
function startViewfinderFeed() {
  if (viewfinderTimer) clearInterval(viewfinderTimer);
  viewfinderTimer = setInterval(refreshViewfinderFrame, 800);
}

function refreshViewfinderFrame() {
  const feedImg = document.getElementById("viewfinderFeed");
  if (!feedImg) return;

  const img = new Image();
  img.onload = () => {
    feedImg.src = img.src;
    const label = document.getElementById("frameStatusLabel");
    if (label) {
      label.innerText = "Active";
      label.className = "metric-val status-ok";
    }
  };
  img.src = `/api/biometric/latest-frame?t=${Date.now()}`;
}

// -------------------------------------------------------------
// Screen Transitions
// -------------------------------------------------------------
function showScreen(screenId) {
  const screens = ["screenWaiting", "screenScanning", "screenVerified", "screenSuccess", "screenError"];
  screens.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      if (id === screenId) el.classList.remove("hidden");
      else el.classList.add("hidden");
    }
  });
}

function resetTerminal() {
  if (autoDebitTimer) {
    clearTimeout(autoDebitTimer);
    autoDebitTimer = null;
  }
  currentAuthenticatedUser = null;
  isPaymentInProgress = false;
  fetch("/api/biometric/pause?paused=false", { method: "POST" }).catch(() => {});
  
  const btnAuto = document.getElementById("btnAutoPay");
  const btnModal = document.getElementById("btnModalPay");
  if (btnAuto) {
    btnAuto.disabled = false;
    btnAuto.innerText = "⚡ 1-Touch Instant Auto-Debit";
  }
  if (btnModal) {
    btnModal.disabled = false;
    btnModal.innerText = "💳 Open Razorpay Checkout Modal";
  }

  showScreen("screenWaiting");
}

function setAmount(val) {
  document.getElementById("payAmount").value = val;
}

// -------------------------------------------------------------
// Real-Time Scan Polling (Event ID Driven - Timezone Independent)
// -------------------------------------------------------------
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollLatestScan, 600);
}

async function pollLatestScan() {
  // If payment or checkout modal is active, don't interrupt
  if (isPaymentInProgress || currentAuthenticatedUser !== null) {
    return;
  }

  try {
    const res = await fetch("/api/biometric/latest");
    if (!res.ok) return;

    const data = await res.json();
    if (!data.event_id) return;

    // Trigger on any new event ID
    if (data.event_id !== lastSeenEventId) {
      lastSeenEventId = data.event_id;
      console.log("[FRONTEND] New scan event detected:", data);

      // Refresh camera viewfinder image immediately
      refreshViewfinderFrame();

      if (data.status === "ENROLLED") {
        handleLiveEnrolledSuccess(data);
      } else if (data.status === "MATCH_FOUND") {
        handleMatchFound(data);
      } else if (data.status === "NO_MATCH") {
        handleNoMatch();
      } else if (data.status === "LOW_QUALITY") {
        handleLowQuality(data.message);
      }
    }
  } catch (err) {
    console.warn("Polling error:", err);
  }
}

function handleMatchFound(data) {
  currentAuthenticatedUser = {
    userId: data.user_id,
    name: data.name || data.user_id,
    confidence: data.confidence || 0.90
  };

  const nameEl = document.getElementById("verifiedUserName");
  const idEl = document.getElementById("verifiedUserId");
  const confEl = document.getElementById("verifiedConfidence");
  const banner = document.getElementById("autoDebitBanner");

  if (nameEl) nameEl.innerText = currentAuthenticatedUser.name;
  if (idEl) idEl.innerText = `Customer ID: ${currentAuthenticatedUser.userId}`;
  if (confEl) {
    const confPercent = (currentAuthenticatedUser.confidence * 100).toFixed(1);
    confEl.innerText = `${confPercent}% Match`;
  }

  showScreen("screenVerified");

  if (currentCheckoutMode === "auto") {
    if (banner) banner.classList.remove("hidden");
    if (autoDebitTimer) clearTimeout(autoDebitTimer);
    autoDebitTimer = setTimeout(() => {
      if (currentAuthenticatedUser && !isPaymentInProgress && currentCheckoutMode === "auto") {
        executeAutoDebit();
      }
    }, 1000);
  } else {
    if (banner) banner.classList.add("hidden");
  }
}

function handleNoMatch() {
  document.getElementById("errorTitle").innerText = "Palm Not Recognized";
  document.getElementById("errorMessage").innerText = "No matching enrolled customer was found for this palm.";
  showScreen("screenError");

  // Auto-reset back to waiting screen after 3.5 seconds
  setTimeout(() => {
    const errScreen = document.getElementById("screenError");
    if (errScreen && !errScreen.classList.contains("hidden")) {
      resetTerminal();
    }
  }, 3500);
}

function handleLowQuality(msg) {
  document.getElementById("errorTitle").innerText = "Positioning / Lighting Issue";
  document.getElementById("errorMessage").innerText = msg || "Please hold your palm open and steady over the camera.";
  showScreen("screenError");

  // Auto-reset back to waiting screen after 3.5 seconds
  setTimeout(() => {
    const errScreen = document.getElementById("screenError");
    if (errScreen && !errScreen.classList.contains("hidden")) {
      resetTerminal();
    }
  }, 3500);
}

function handleLiveEnrolledSuccess(data) {
  isEnrollingActive = false;
  const waitingBox = document.getElementById("enrollWaitingState");
  const resultBox = document.getElementById("enrollResult");
  const btn = document.getElementById("btnLiveEnroll");

  if (waitingBox) waitingBox.classList.add("hidden");
  if (btn) btn.classList.remove("hidden");

  if (resultBox) {
    resultBox.className = "alert-box success";
    resultBox.innerHTML = `<strong>[✓] Enrolled Successfully from ESP32 Camera!</strong><br>Customer '${data.name || data.user_id}' is now registered. You can now use the scanner to pay!`;
    resultBox.classList.remove("hidden");
  }

  setTimeout(() => {
    switchTab("terminal");
    resetTerminal();
  }, 2500);
}

// -------------------------------------------------------------
// Live Hardware Scan Enrollment Flow
// -------------------------------------------------------------
async function handleLiveEnrollment(e) {
  e.preventDefault();

  const userId = document.getElementById("enrollUserId").value.trim();
  const name = document.getElementById("enrollName").value.trim();
  const email = document.getElementById("enrollEmail").value.trim();
  const resultBox = document.getElementById("enrollResult");
  const waitingBox = document.getElementById("enrollWaitingState");
  const btn = document.getElementById("btnLiveEnroll");

  resultBox.className = "alert-box hidden";
  btn.classList.add("hidden");
  waitingBox.classList.remove("hidden");
  isEnrollingActive = true;

  try {
    const res = await fetch("/api/users/start-enrollment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        name: name,
        email: email || null
      })
    });

    if (!res.ok) {
      throw new Error("Failed to arm enrollment mode.");
    }
  } catch (err) {
    waitingBox.classList.add("hidden");
    btn.classList.remove("hidden");
    resultBox.className = "alert-box error";
    resultBox.innerText = `[X] Error: ${err.message}`;
    resultBox.classList.remove("hidden");
    isEnrollingActive = false;
  }
}

async function cancelLiveEnrollment() {
  await fetch("/api/users/cancel-enrollment", { method: "POST" });
  document.getElementById("enrollWaitingState").classList.add("hidden");
  document.getElementById("btnLiveEnroll").classList.remove("hidden");
  isEnrollingActive = false;
}

// -------------------------------------------------------------
// Payment Execution Flows (Dual Option Support)
// -------------------------------------------------------------

// OPTION 1: 1-Touch Contactless Instant Auto-Debit
async function executeAutoDebit() {
  if (!currentAuthenticatedUser) {
    alert("No biometrically authenticated user.");
    resetTerminal();
    return;
  }

  const amountInput = document.getElementById("payAmount");
  const amountVal = parseFloat(amountInput ? amountInput.value : 100);
  if (isNaN(amountVal) || amountVal <= 0) {
    alert("Please enter a valid amount greater than ₹0.");
    return;
  }

  const btnAuto = document.getElementById("btnAutoPay");
  if (btnAuto) {
    btnAuto.disabled = true;
    btnAuto.innerText = "⚡ AUTHORIZING AUTO-DEBIT...";
  }
  isPaymentInProgress = true;

  try {
    const orderRes = await fetch("/api/payments/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: currentAuthenticatedUser.userId,
        amount: amountVal
      })
    });

    if (!orderRes.ok) {
      const err = await orderRes.json().catch(() => ({}));
      throw new Error(err.detail || "Order creation failed.");
    }

    const orderData = await orderRes.json();
    console.log("[POS 1-Touch] Order registered:", orderData.razorpay_order_id);

    const paymentId = "pay_bio_" + Math.random().toString(36).substring(2, 11);

    setTimeout(async () => {
      await verifyServerPayment({
        razorpay_order_id: orderData.razorpay_order_id,
        razorpay_payment_id: paymentId,
        razorpay_signature: "biometric_contactless_token"
      }, amountVal);
    }, 600);

  } catch (error) {
    console.warn("[POS 1-Touch] Error:", error.message);
    alert("Payment Error: " + error.message);
    isPaymentInProgress = false;
    if (btnAuto) {
      btnAuto.disabled = false;
      btnAuto.innerText = "⚡ 1-Touch Instant Auto-Debit";
    }
  }
}

// OPTION 2: Razorpay Interactive Checkout Modal
async function executeRazorpayModal() {
  if (autoDebitTimer) {
    clearTimeout(autoDebitTimer);
    autoDebitTimer = null;
  }
  const banner = document.getElementById("autoDebitBanner");
  if (banner) banner.classList.add("hidden");

  if (!currentAuthenticatedUser) {
    alert("No biometrically authenticated user.");
    resetTerminal();
    return;
  }

  const amountInput = document.getElementById("payAmount");
  const amountVal = parseFloat(amountInput ? amountInput.value : 100);
  if (isNaN(amountVal) || amountVal <= 0) {
    alert("Please enter a valid amount greater than ₹0.");
    return;
  }

  const btnModal = document.getElementById("btnModalPay");
  if (btnModal) {
    btnModal.disabled = true;
    btnModal.innerText = "Opening Razorpay...";
  }
  isPaymentInProgress = true;

  try {
    const orderRes = await fetch("/api/payments/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: currentAuthenticatedUser.userId,
        amount: amountVal
      })
    });

    if (!orderRes.ok) {
      const err = await orderRes.json().catch(() => ({}));
      throw new Error(err.detail || "Order creation failed.");
    }

    const orderData = await orderRes.json();
    console.log("[POS Modal] Order registered:", orderData.razorpay_order_id);

    if (typeof Razorpay === "undefined") {
      throw new Error("Razorpay Checkout SDK not loaded.");
    }

    const options = {
      key: orderData.key_id,
      amount: orderData.amount,
      currency: orderData.currency,
      name: "PalmPay Biometrics",
      description: `Payment by ${orderData.user_name}`,
      order_id: orderData.razorpay_order_id,
      handler: async function (response) {
        await verifyServerPayment(response, amountVal);
      },
      prefill: {
        name: orderData.user_name,
        contact: "9999999999"
      },
      theme: {
        color: "#698F3F"
      },
      modal: {
        ondismiss: function() {
          isPaymentInProgress = false;
          if (btnModal) {
            btnModal.disabled = false;
            btnModal.innerText = "💳 Open Razorpay Checkout Modal";
          }
        }
      }
    };

    const rzp = new Razorpay(options);
    rzp.on("payment.failed", function (resp) {
      alert("Payment failed: " + (resp.error ? resp.error.description : "Cancelled"));
      isPaymentInProgress = false;
      if (btnModal) {
        btnModal.disabled = false;
        btnModal.innerText = "💳 Open Razorpay Checkout Modal";
      }
    });
    rzp.open();

  } catch (error) {
    console.warn("[POS Modal] Error:", error.message);
    alert("Razorpay Modal Notice: " + error.message);
    isPaymentInProgress = false;
    if (btnModal) {
      btnModal.disabled = false;
      btnModal.innerText = "💳 Open Razorpay Checkout Modal";
    }
  }
}

async function verifyServerPayment(paymentData, amount) {
  try {
    const verifyRes = await fetch("/api/payments/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        razorpay_order_id: paymentData.razorpay_order_id,
        razorpay_payment_id: paymentData.razorpay_payment_id,
        razorpay_signature: paymentData.razorpay_signature
      })
    });

    const verifyResult = await verifyRes.json();

    if (verifyRes.ok && verifyResult.status === "SUCCESS") {
      document.getElementById("receiptAmount").innerText = `₹${amount.toFixed(2)}`;
      document.getElementById("receiptUser").innerText = currentAuthenticatedUser ? `${currentAuthenticatedUser.name} (${currentAuthenticatedUser.userId})` : "Verified User";
      document.getElementById("receiptPaymentId").innerText = verifyResult.payment_id || paymentData.razorpay_payment_id;
      document.getElementById("receiptOrderId").innerText = verifyResult.order_id || paymentData.razorpay_order_id;

      showScreen("screenSuccess");
      isPaymentInProgress = false;

      // Auto-reset back to waiting screen after 5.5 seconds
      setTimeout(() => {
        const successScreen = document.getElementById("screenSuccess");
        if (successScreen && !successScreen.classList.contains("hidden")) {
          resetTerminal();
        }
      }, 5500);
    } else {
      alert("Payment verification result: " + (verifyResult.message || "Failed"));
      resetTerminal();
    }
  } catch (err) {
    alert("Verification network error: " + err.message);
    resetTerminal();
  } finally {
    isPaymentInProgress = false;
    const btnAuto = document.getElementById("btnAutoPay");
    const btnModal = document.getElementById("btnModalPay");
    if (btnAuto) {
      btnAuto.disabled = false;
      btnAuto.innerText = "⚡ 1-Touch Instant Auto-Debit";
    }
    if (btnModal) {
      btnModal.disabled = false;
      btnModal.innerText = "💳 Open Razorpay Checkout Modal";
    }
  }
}

// -------------------------------------------------------------
// Manual Simulation (Test Mode without Hardware)
// -------------------------------------------------------------
async function triggerManualTestScan() {
  showScreen("screenScanning");

  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = "#1e1e1e";
  ctx.fillRect(0, 0, 320, 240);

  ctx.fillStyle = "#d2a679";
  ctx.beginPath();
  ctx.ellipse(160, 130, 60, 70, 0, 0, 2 * Math.PI);
  ctx.fill();

  ctx.lineWidth = 18;
  ctx.strokeStyle = "#d2a679";
  ctx.lineCap = "round";
  const fingers = [[115, 60], [135, 45], [160, 40], [185, 45], [205, 60]];
  fingers.forEach(([fx, fy]) => {
    ctx.beginPath();
    ctx.moveTo(160, 130);
    ctx.lineTo(fx, fy);
    ctx.stroke();
  });

  ctx.lineWidth = 2;
  ctx.strokeStyle = "#8c5c36";
  ctx.beginPath();
  ctx.moveTo(130, 120);
  ctx.lineTo(190, 115);
  ctx.moveTo(135, 140);
  ctx.lineTo(185, 145);
  ctx.stroke();

  canvas.toBlob(async (blob) => {
    const formData = new FormData();
    formData.append("file", blob, "test_palm.jpg");

    try {
      const res = await fetch("/api/biometric/test", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      refreshViewfinderFrame();

      if (data.status === "MATCH_FOUND") {
        handleMatchFound(data);
      } else if (data.status === "NO_MATCH") {
        handleNoMatch();
      } else {
        handleLowQuality(data.message);
      }
    } catch (e) {
      handleLowQuality("Manual simulation connection error.");
    }
  }, "image/jpeg");
}
