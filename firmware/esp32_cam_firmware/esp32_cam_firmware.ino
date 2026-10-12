/**
 * ============================================================================
 * PALM-BASED BIOMETRIC PAYMENT SYSTEM - HIGH SPEED ESP32-CAM FIRMWARE
 * ============================================================================
 * Hardware: AI Thinker ESP32-CAM + IR Sensor + LED + Buzzer
 * Protocol: Fast Raw RGB565 Stream (320x240, 153600 bytes) over HTTP to FastAPI
 * ============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// ----------------------------------------------------------------------------
// 1. NETWORK & BACKEND CONFIGURATION
// ----------------------------------------------------------------------------
const char* WIFI_SSID     = "OnePlus 13 162A";                        // Your 2.4GHz Hotspot
const char* WIFI_PASSWORD = "9902550343";                 // <-- Enter your hotspot password

// Computer's IP address on this network:
const char* BACKEND_URL   = "http://10.216.82.24:8000/api/biometric/scan";

// Device Authorization Key
const char* DEVICE_API_KEY = "esp32_palm_auth_secret_key_2026";

// ----------------------------------------------------------------------------
// 2. CAMERA PIN CONFIGURATION (AI Thinker Model)
// ----------------------------------------------------------------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ----------------------------------------------------------------------------
// 3. PERIPHERAL PIN DEFINITIONS
// ----------------------------------------------------------------------------
const int irPin     = 13; // Active LOW when palm is present
const int buzzerPin = 14; // Active HIGH for buzzer
const int ledPin    = 15; // PWM indicator LED

const int pwmFreq           = 5000;
const int pwmResolution     = 8;
const int safeLedBrightness = 15; // Safe current

WiFiClient wifiClient;
unsigned long lastWiFiCheck = 0;

// ----------------------------------------------------------------------------
// 4. FEEDBACK UTILITIES
// ----------------------------------------------------------------------------
void toneBeep(int count, int onDurationMs, int offDurationMs) {
  for (int i = 0; i < count; i++) {
    digitalWrite(buzzerPin, HIGH);
    delay(onDurationMs);
    digitalWrite(buzzerPin, LOW);
    if (i < count - 1) delay(offDurationMs);
  }
}

void giveFeedback(const String& status) {
  if (status == "MATCH_FOUND" || status == "ENROLLED") {
    Serial.println("[FEEDBACK] -> SUCCESS (Double Beep)");
    ledcWrite(ledPin, safeLedBrightness);
    toneBeep(2, 80, 70);
    ledcWrite(ledPin, 0);
  } else if (status == "NO_MATCH") {
    Serial.println("[FEEDBACK] -> NO_MATCH (Rejection Tone)");
    toneBeep(1, 250, 0);
  } else if (status == "LOW_QUALITY") {
    Serial.println("[FEEDBACK] -> LOW_QUALITY (Warning Beeps)");
    toneBeep(3, 40, 40);
  } else {
    Serial.println("[FEEDBACK] -> ERROR (Long Tone)");
    toneBeep(1, 400, 0);
  }
}

// ----------------------------------------------------------------------------
// 5. BULLETPROOF WIFI CONNECTION MANAGER
// ----------------------------------------------------------------------------
void connectToWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("\n[*] Connecting to WiFi: \"%s\" ...\n", WIFI_SSID);

  // Clean disconnect first to avoid 'sta is connecting, cannot set config' errors
  WiFi.disconnect(true, true);
  delay(200);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // Minimum latency
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  // Wait up to 15 seconds for connection
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[✓] WiFi Connected! IP: %s | Signal: %d dBm\n", 
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    toneBeep(1, 80, 0);
  } else {
    Serial.printf("\n[X] WiFi Connection Failed (Status: %d)!\n", WiFi.status());
    Serial.println("    -> Tip: Ensure phone hotspot is ON, set to 2.4 GHz, and Security is WPA2-Personal.");
  }
}

// ----------------------------------------------------------------------------
// 6. SETUP
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==================================================");
  Serial.println("   HIGH-SPEED PALM BIOMETRIC SCANNER (ESP32-CAM)  ");
  Serial.println("==================================================");

  // 1. Initialize Camera (RGB565 320x240 STRICTLY)
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;

  // STRICT REQUIREMENT: RAW RGB565 at QVGA (320x240)
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size   = FRAMESIZE_QVGA; // 320x240
  config.fb_count     = 1;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[X] Camera Init Failed! Error: 0x%x\n", err);
    while (true) {
      toneBeep(2, 100, 100);
      delay(2000);
    }
  }

  sensor_t * s = esp_camera_sensor_get();
  if (s != NULL) {
    Serial.printf("[✓] Camera Ready. PID: 0x%x\n", s->id.PID);
  }

  // 2. Initialize Peripherals
  pinMode(irPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  digitalWrite(buzzerPin, LOW);

  ledcAttach(ledPin, pwmFreq, pwmResolution);
  ledcWrite(ledPin, 0);

  // 3. Connect to WiFi
  connectToWiFi();

  Serial.println("[✓] Ready! Place palm over sensor to scan.\n");
}

// ----------------------------------------------------------------------------
// 7. FAST SCAN & TRANSMISSION
// ----------------------------------------------------------------------------
void transmitFrame(camera_fb_t * fb) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[X] WiFi disconnected! Cannot transmit.");
    giveFeedback("ERROR");
    return;
  }

  unsigned long t0 = millis();

  HTTPClient http;
  http.begin(wifiClient, BACKEND_URL);
  http.setConnectTimeout(2500); // 2.5s connect timeout
  http.setTimeout(4000);        // 4s request timeout
  http.setReuse(false);

  // Set HTTP Headers
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("Content-Length", String(fb->len));
  http.addHeader("X-Device-Key", DEVICE_API_KEY);
  http.addHeader("X-Image-Width", "320");
  http.addHeader("X-Image-Height", "240");
  http.addHeader("X-Pixel-Format", "RGB565");

  Serial.printf("[*] Streaming %u bytes to server...\n", fb->len);
  int httpCode = http.POST(fb->buf, fb->len);
  unsigned long elapsed = millis() - t0;

  if (httpCode > 0) {
    String payload = http.getString();
    Serial.printf("[✓] Server Responded (%lums): HTTP %d -> %s\n", elapsed, httpCode, payload.c_str());

    if (payload.indexOf("\"MATCH_FOUND\"") >= 0 || payload.indexOf("\"ENROLLED\"") >= 0) {
      giveFeedback("MATCH_FOUND");
    } else if (payload.indexOf("\"LOW_QUALITY\"") >= 0) {
      giveFeedback("LOW_QUALITY");
    } else if (payload.indexOf("\"NO_MATCH\"") >= 0) {
      giveFeedback("NO_MATCH");
    } else {
      giveFeedback("ERROR");
    }
  } else {
    Serial.printf("[X] HTTP POST Failed (%lums): %s (Code %d)\n", 
                  elapsed, http.errorToString(httpCode).c_str(), httpCode);
    giveFeedback("ERROR");
  }
  http.end();
}

// ----------------------------------------------------------------------------
// 8. MAIN LOOP
// ----------------------------------------------------------------------------
void loop() {
  // Check and reconnect WiFi without flooding the state machine
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWiFiCheck > 8000) {
      lastWiFiCheck = millis();
      connectToWiFi();
    }
  }

  int irState = digitalRead(irPin);

  // IR Sensor Active (LOW indicates object/palm detected)
  if (irState == LOW) {
    Serial.println("\n--------------------------------------------------");
    Serial.println("[TRIGGER] Palm Detected by IR Sensor!");

    // 1. Turn on illumination LED
    ledcWrite(ledPin, safeLedBrightness);
    digitalWrite(buzzerPin, HIGH);
    delay(60);
    digitalWrite(buzzerPin, LOW);

    // 2. Capture Frame
    unsigned long capT0 = millis();
    camera_fb_t * fb = esp_camera_fb_get();
    unsigned long capElapsed = millis() - capT0;

    if (!fb) {
      Serial.println("[X] Frame Capture Failed!");
      giveFeedback("ERROR");
      ledcWrite(ledPin, 0);
      delay(1500);
      return;
    }

    Serial.printf("[✓] Captured in %lums: %u bytes (%dx%d)\n", capElapsed, fb->len, fb->width, fb->height);

    // 3. Transmit Frame
    transmitFrame(fb);

    // 4. Return Framebuffer
    esp_camera_fb_return(fb);

    // 5. Turn Off LED
    ledcWrite(ledPin, 0);

    // 6. Cooldown Delay
    Serial.println("[*] Cooldown (1.5s)... Ready for next scan.");
    delay(1500);
  }

  delay(60);
}
