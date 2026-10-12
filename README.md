# 🖐️ PalmPay - Palm-Based Biometric Payment System

A production-grade, end-to-end contactless biometric payment terminal powered by **AI Thinker ESP32-CAM**, **FastAPI**, **OpenCV**, **NumPy**, **SQLite**, and **Razorpay**.

---

## 📑 Table of Contents
1. [System Architecture](#-system-architecture)
2. [Hardware Components & Wiring](#-hardware-components--wiring)
3. [RGB565 Raw Frame Protocol](#-rgb565-raw-frame-protocol)
4. [Biometric Recognition Pipeline](#-biometric-recognition-pipeline)
5. [Backend Installation & Setup](#-backend-installation--setup)
6. [ESP32-CAM Firmware Upload](#-esp32-cam-firmware-upload)
7. [Razorpay Payment Gateway Setup](#-razorpay-payment-gateway-setup)
8. [Running the Application](#-running-the-application)
9. [Automated Testing Suite](#-automated-testing-suite)
10. [Docker Deployment](#-docker-deployment)
11. [REST API Reference](#-rest-api-reference)
12. [Security & Privacy](#-security--privacy)

---

## 🏗 System Architecture

```
                    ┌───────────────────────────────────┐
                    │       ESP32-CAM TERMINAL          │
                    │                                   │
                    │  • IR Obstacle Sensor (GPIO 13)   │
                    │  • Raw RGB565 Camera (320x240)    │
                    │  • Illumination LED (GPIO 15)     │
                    │  • Piezo Buzzer (GPIO 14)         │
                    └─────────────────┬─────────────────┘
                                      │
                                      │ WiFi / HTTP
                                      │ POST /api/biometric/scan
                                      │ Content-Type: application/octet-stream
                                      │ Raw 153,600 Bytes
                                      ▼
                    ┌───────────────────────────────────┐
                    │      FASTAPI BACKEND GATEWAY      │
                    │                                   │
                    │  • RGB565 to BGR OpenCV Decoder   │
                    │  • Image Quality Validation       │
                    │  • Palm Skin Segmentation (YCrCb) │
                    │  • CLAHE + Multi-Scale Gabor Bank │
                    │  • L2-Normalized Feature Matching │
                    │  • SQLite User & Template Store   │
                    │  • Razorpay Order & Signatures    │
                    └─────────────────┬─────────────────┘
                                      │
                                      │ Polling / SSE (JSON)
                                      ▼
                    ┌───────────────────────────────────┐
                    │      FRONTEND CHECKOUT UI         │
                    │                                   │
                    │  • Live Scan Terminal State       │
                    │  • Identity & Confidence Card     │
                    │  • Dynamic INR Amount Field       │
                    │  • Razorpay Standard Checkout SDK │
                    └─────────────────┬─────────────────┘
                                      │
                                      │ Server-side Signature Verification
                                      ▼
                    ┌───────────────────────────────────┐
                    │          RAZORPAY API             │
                    └───────────────────────────────────┘
```

---

## 🔌 Hardware Components & Wiring

### Bill of Materials:
* **AI Thinker ESP32-CAM** (OV2640 / OV7670 Sensor with 4MB PSRAM)
* **FTDI USB-to-TTL Programmer** (or ESP32-CAM-MB baseboard)
* **Active Low IR Obstacle Sensor Module** (3-pin: VCC, GND, OUT)
* **Piezoelectric Buzzer** (Active 5V)
* **White/Green LED**
* **External 5V / 2A Power Source** (or high-power USB port)

### Pin Mapping:
| Component Pin | ESP32-CAM GPIO | Notes |
| :--- | :--- | :--- |
| **IR Sensor OUT** | **GPIO 13** | Reads `LOW` when palm is placed above sensor |
| **Buzzer (+)** | **GPIO 14** | `HIGH` triggers tone (Active Buzzer) |
| **LED (+)** | **GPIO 15** | Driven via PWM `ledcWrite` at safe duty cycle (15/255) |
| **GND (Common)** | **GND** | Connect all component GNDs together |
| **5V Power** | **5V / VCC** | Connect to solid 5.0V source (Measured ~4.96V) |
| **GPIO 0** | **GND** | *Flashing Mode Only* (Disconnect after uploading code) |

---

## 🖼 RGB565 Raw Frame Protocol

The ESP32 captures uncompressed **RGB565** format to maintain camera reliability.

### Mathematical Specification:
* **Resolution:** $320 \times 240$ (QVGA)
* **Bytes per Pixel:** 2 bytes (16-bit)
* **Total Frame Size:** $320 \times 240 \times 2 = 153,600\text{ bytes}$

$$\text{Pixel}_{16} = \underbrace{R_4 R_3 R_2 R_1 R_0}_{5\text{ bits}} \; \underbrace{G_5 G_4 G_3 G_2 G_1 G_0}_{6\text{ bits}} \; \underbrace{B_4 B_3 B_2 B_1 B_0}_{5\text{ bits}}$$

### Reconstruction to 8-bit BGR:
```python
R8 = (R5 << 3) | (R5 >> 2)
G8 = (G6 << 2) | (G6 >> 4)
B8 = (B5 << 3) | (B5 >> 2)
```

The vectorized decoder in `backend/app/services/rgb565_decoder.py` performs this conversion into an OpenCV `(240, 320, 3)` `uint8` array in less than **2.1 milliseconds**.

---

## 🧬 Biometric Recognition Pipeline

1. **Decoding:** Converts incoming binary payload to OpenCV BGR.
2. **Quality Verification:** Checks illumination bounds ($20 \le \bar{I} \le 245$) and standard deviation contrast ($\sigma \ge 15.0$).
3. **Skin Segmentation:** Fuses YCrCb ($Cr \in [133, 175], Cb \in [77, 127]$) with HSV masks and morphological filtering.
4. **Center Localization:** Executes Euclidean Distance Transform to compute the maximum inscripted palm circle.
5. **Normalization:** Crops $128 \times 128$ Region of Interest (ROI) and applies CLAHE ($3.0$ clip limit).
6. **Feature Extraction:** Evaluates 12 Gabor wavelet responses (multi-orientation: $0^\circ, 30^\circ, 60^\circ, 90^\circ, 120^\circ, 150^\circ$) and Sobel spatial gradients.
7. **Similarity Scoring:** Computes Cosine Similarity $\cos(\theta) = u \cdot v$ on L2-normalized feature vectors against the enrolled database with threshold $\ge 0.85$.

---

## 🚀 Backend Installation & Setup

### 1. Prerequisites:
* Python 3.11+
* `uv` or `pip`

### 2. Setup Virtual Environment:
```powershell
# Navigate to workspace
cd c:\Aniketh\Coding\Embedded

# Create virtual environment and install dependencies
uv venv backend/.venv --python 3.11
uv pip install -r backend/requirements.txt --python backend/.venv/Scripts/python.exe
```

### 3. Configure Environment Variables:
Edit `backend/.env`:
```env
BACKEND_URL=http://localhost:8000
HOST=0.0.0.0
PORT=8000

DEVICE_API_KEY=esp32_palm_auth_secret_key_2026
DATABASE_URL=sqlite:///./data/palm_biometric.db
MATCH_THRESHOLD=0.85

RAZORPAY_KEY_ID=rzp_test_mock_key_id
RAZORPAY_KEY_SECRET=rzp_test_mock_secret_key

DEBUG=true
STORE_DEBUG_IMAGES=false
```

---

## ⚡ Running the Application

### Start the FastAPI Backend:
```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

* **Interactive Terminal UI:** [http://localhost:8000](http://localhost:8000)
* **Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 📲 ESP32-CAM Firmware Upload

1. Open [`firmware/esp32_cam_firmware/esp32_cam_firmware.ino`](file:///c:/Aniketh/Coding/Embedded/firmware/esp32_cam_firmware/esp32_cam_firmware.ino) in the Arduino IDE.
2. Configure your WiFi credentials and your computer's local IP address:
   ```cpp
   const char* WIFI_SSID     = "Your_WiFi_Name";
   const char* WIFI_PASSWORD = "Your_WiFi_Password";
   const char* BACKEND_URL   = "http://192.168.1.100:8000/api/biometric/scan";
   ```
3. Set **Tools** menu settings:
   * **Board:** `AI Thinker ESP32-CAM`
   * **Flash Frequency:** `80MHz`
   * **Upload Speed:** `115200`
4. Connect **GPIO 0 to GND**, press **RST** button on ESP32, and click **Upload**.
5. Disconnect **GPIO 0 from GND**, open **Serial Monitor (115200 baud)**, and press **RST**.

---

## 💳 Razorpay Payment Gateway Setup

### Test Mode Integration:
1. Log in to your [Razorpay Dashboard](https://dashboard.razorpay.com/).
2. Switch to **Test Mode**.
3. Generate **Key ID** and **Key Secret** under *Settings $\rightarrow$ API Keys*.
4. Paste them into `backend/.env`:
   ```env
   RAZORPAY_KEY_ID=rzp_test_yourKeyHere
   RAZORPAY_KEY_SECRET=yourSecretKeyHere
   ```
5. Restart the backend. All orders will now create live test transactions in Razorpay.

---

## 🧪 Automated Testing Suite

Run the full automated test suite covering decoders, biometric extractors, users CRUD, and Razorpay HMAC signature verification:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

Output:
```
backend/tests/test_biometric_api.py::test_health_check PASSED
backend/tests/test_biometric_api.py::test_esp32_scan_unauthorized PASSED
backend/tests/test_biometric_api.py::test_esp32_scan_invalid_format_header PASSED
backend/tests/test_biometric_api.py::test_esp32_scan_invalid_size PASSED
backend/tests/test_biometric_api.py::test_esp32_scan_flow_enroll_and_match PASSED
backend/tests/test_palm_processing.py::test_validate_image_quality PASSED
backend/tests/test_palm_processing.py::test_palm_feature_extractor PASSED
backend/tests/test_palm_processing.py::test_feature_serialization_roundtrip PASSED
backend/tests/test_payments_api.py::test_payment_lifecycle PASSED
backend/tests/test_payments_api.py::test_create_order_invalid_amount PASSED
backend/tests/test_rgb565_decoder.py::test_rgb565_exact_size_qvga PASSED
backend/tests/test_rgb565_decoder.py::test_rgb565_rejects_invalid_size PASSED
backend/tests/test_rgb565_decoder.py::test_rgb565_known_colors_little_endian PASSED
backend/tests/test_rgb565_decoder.py::test_rgb565_roundtrip_encode_decode PASSED
backend/tests/test_users_api.py::test_user_crud_and_biometric_purge PASSED
backend/tests/test_users_api.py::test_get_nonexistent_user PASSED

======================== 16 passed in 0.41s ========================
```

---

## 🐳 Docker Deployment

To run the complete system in a standalone Docker container:

```bash
docker compose up --build -d
```

Check status and logs:
```bash
docker compose logs -f
```

---

## 📡 REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Server health and decoder status |
| `POST` | `/api/biometric/scan` | ESP32 raw RGB565 stream receiver |
| `POST` | `/api/biometric/test` | Multipart upload for manual image testing |
| `GET` | `/api/biometric/latest` | Real-time frontend scan polling |
| `POST` | `/api/users/enroll` | Enroll user with palm reference photo |
| `GET` | `/api/users/{user_id}` | Fetch user profile and template count |
| `DELETE` | `/api/users/{user_id}/biometric` | Purge biometric templates (Privacy compliance) |
| `POST` | `/api/payments/create-order` | Generate Razorpay order for authenticated user |
| `POST` | `/api/payments/verify` | Server-side HMAC-SHA256 signature verification |
| `GET` | `/api/payments/{payment_id}` | Fetch transaction receipt |

---

## 🔒 Security & Privacy

1. **Biometric Privacy:** Raw palm frames are processed in-memory, converted to Gabor/Sobel float32 feature vectors, and immediately discarded. No raw biometric photos are persisted unless explicit debug logging is enabled.
2. **Device Authentication:** Only requests bearing a valid `X-Device-Key` corresponding to a registered ESP32 are accepted.
3. **Cryptographic Signatures:** Payments are only marked `SUCCESS` after valid HMAC-SHA256 signature verification against the backend `RAZORPAY_KEY_SECRET`.
4. **Data Purge:** Full GDPR/DPDP biometric deletion endpoint is available at `DELETE /api/users/{user_id}/biometric`.
