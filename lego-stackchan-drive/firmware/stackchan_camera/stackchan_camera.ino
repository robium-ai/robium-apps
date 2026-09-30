// MIT, Copyright (c) 2026 robium. Camera transport proof of concept.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5StackChan.h>
#include <WiFi.h>
#include <Preferences.h>
#include <ESPmDNS.h>
#include <esp_camera.h>
#include <esp_http_server.h>
#include <esp_timer.h>
#include <img_converters.h>
#include <math.h>
#include <lwip/sockets.h>
#include <lwip/tcp.h>
#include <esp_wifi.h>
#include "pins.h"

Preferences prefs;
String streamKey;
bool cameraReady = false;
httpd_handle_t server = nullptr;
uint32_t sequence = 0;
uint32_t framesSent = 0;
portMUX_TYPE profileMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t targetFps = 8, jpegQuality = 75;
uint32_t wifiDisconnects = 0, lastWifiReason = 0;
int streamNoDelay = -1;
uint32_t bootId;
bool directWifi = false;
uint32_t directWifiStarted = 0, directWifiLeaseMs = 0;

bool networkReady() {
  return directWifi || WiFi.status() == WL_CONNECTED;
}

String networkAddress() {
  return directWifi ? WiFi.softAPIP().toString() : WiFi.localIP().toString();
}
struct EncodedFrame {
  uint8_t* jpeg = nullptr;
  size_t size = 0;
  uint64_t sensorUs = 0;
  uint32_t sequence = 0, encodeUs = 0, captureWaitUs = 0, missedSlots = 0;
  uint32_t fps = 8, quality = 75;
};
EncodedFrame latestFrame;
SemaphoreHandle_t frameMutex;
SemaphoreHandle_t frameAvailable;

// Encode on a fixed schedule independently of TCP. Keep just the newest image:
// a slow receiver skips counted sequences instead of accumulating old video.
void captureFrames(void*) {
  uint64_t nextSlot = esp_timer_get_time();
  uint32_t missedSlots = 0;
  while (true) {
    uint32_t fps, quality;
    portENTER_CRITICAL(&profileMux);
    fps = targetFps; quality = jpegQuality;
    portEXIT_CRITICAL(&profileMux);
    uint32_t periodUs = 1000000 / fps;
    uint64_t now = esp_timer_get_time();
    if (now < nextSlot) delay((nextSlot - now + 999) / 1000);
    else missedSlots += (now - nextSlot) / periodUs;
    nextSlot = esp_timer_get_time() + periodUs;
    uint64_t started = esp_timer_get_time();
    camera_fb_t* fb = esp_camera_fb_get();
    uint32_t captureWaitUs = esp_timer_get_time() - started;
    if (!fb) { missedSlots++; continue; }
    EncodedFrame frame;
    frame.sensorUs = uint64_t(fb->timestamp.tv_sec) * 1000000 + fb->timestamp.tv_usec;
    started = esp_timer_get_time();
    bool ok = frame2jpg(fb, quality, &frame.jpeg, &frame.size);
    frame.encodeUs = esp_timer_get_time() - started;
    esp_camera_fb_return(fb);
    if (!ok || !frame.jpeg) { free(frame.jpeg); missedSlots++; continue; }
    frame.sequence = sequence++;
    frame.fps = fps; frame.quality = quality;
    frame.captureWaitUs = captureWaitUs;
    frame.missedSlots = missedSlots;
    xSemaphoreTake(frameMutex, portMAX_DELAY);
    uint8_t* old = latestFrame.jpeg;
    latestFrame = frame;
    xSemaphoreGive(frameMutex);
    free(old);
    xSemaphoreGive(frameAvailable);
  }
}
httpd_handle_t headServer = nullptr;
portMUX_TYPE headMux = portMUX_INITIALIZER_UNLOCKED;
float headPan = 0, headTilt = 0;
uint32_t headReceived = 0;
float headYaw = 0, headPitch = 0;
bool headHold = true;
bool headReleased = true;
bool headReleaseApplied = false;
bool headMoving = false;
bool servoPowerEnabled = true, servoPowerVerified = false;
uint32_t headRestartAt = 0;


bool authorized(httpd_req_t* req) {
  char provided[100] = {};
  httpd_req_get_hdr_value_str(req, "X-Stream-Key", provided, sizeof(provided));
  return streamKey.length() && streamKey == provided;
}

#include "speech.h"
#include "faces.h"

// Temporary, explicit benchmark settings. A reboot returns to 8 FPS / Q75;
// profiles never adapt automatically while a recording is being collected.
esp_err_t cameraProfile(httpd_req_t* req) {
  if (!authorized(req)) {
    return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Forbidden");
  }
  if (req->method == HTTP_POST) {
    if (req->content_len <= 0 || req->content_len > 100) {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid profile length");
    }
    char body[101] = {};
    int received = 0;
    while (received < req->content_len) {
      int count = httpd_req_recv(req, body + received, req->content_len - received);
      if (count <= 0) return ESP_FAIL;
      received += count;
    }
    JsonDocument input;
    if (deserializeJson(input, body) || !input["fps"].is<int>() || !input["quality"].is<int>()) {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected integer fps and quality");
    }
    int fps = input["fps"], quality = input["quality"];
    if (fps < 2 || fps > 10 || quality < 35 || quality > 85) {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "FPS 2..10; quality 35..85");
    }
    portENTER_CRITICAL(&profileMux);
    targetFps = fps; jpegQuality = quality;
    portEXIT_CRITICAL(&profileMux);
  }
  JsonDocument out;
  uint32_t fps, quality, disconnects, reason;
  int noDelay;
  portENTER_CRITICAL(&profileMux);
  fps = targetFps; quality = jpegQuality;
  disconnects = wifiDisconnects; reason = lastWifiReason;
  noDelay = streamNoDelay;
  portEXIT_CRITICAL(&profileMux);
  out["fps"] = fps; out["quality"] = quality;
  out["wifi_disconnects"] = disconnects; out["last_wifi_reason"] = reason;
  out["tcp_no_delay"] = noDelay;
  wifi_ps_type_t powerSave;
  out["wifi_power_save_mode"] = esp_wifi_get_ps(&powerSave) == ESP_OK ? int(powerSave) : -1;
  if (!directWifi) out["rssi_dbm"] = WiFi.RSSI();
  out["network_mode"] = directWifi ? "ap" : "station";
  out["ap_clients"] = directWifi ? WiFi.softAPgetStationNum() : 0;
  out["wifi_connected"] = networkReady();
  out["free_heap"] = ESP.getFreeHeap();
  out["minimum_free_heap"] = ESP.getMinFreeHeap();
  out["boot_id"] = bootId;
  out["firmware"] = "0.6.7";
  String encoded;
  serializeJson(out, encoded);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, encoded.c_str(), encoded.length());
}

esp_err_t headControl(httpd_req_t* req) {
  if (!authorized(req)) {
    httpd_resp_set_status(req, "403 Forbidden");
    return httpd_resp_send(req, "Forbidden", HTTPD_RESP_USE_STRLEN);
  }
  if (req->method == HTTP_POST) {
    if (req->content_len <= 0 || req->content_len > 160) {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid command length");
    }
    char body[161] = {};
    int received = 0;
    while (received < req->content_len) {
      int count = httpd_req_recv(req, body + received, req->content_len - received);
      if (count <= 0) return ESP_FAIL;
      received += count;
    }
    JsonDocument input;
    if (deserializeJson(input, body) || !input["pan"].is<float>() || !input["tilt"].is<float>()) {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected pan and tilt");
    }
    String mode = input["mode"] | "";
    if (mode != "absolute" && mode != "hold" && mode != "release" && mode != "resume") {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected absolute, hold, release or resume mode");
    }
    float pan = input["pan"], tilt = input["tilt"];
    if (!isfinite(pan) || !isfinite(tilt) || fabsf(pan) > 1 || fabsf(tilt) > 1) {
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Axes outside -1..1");
    }
    if (headReleased && mode == "absolute") {
      httpd_resp_set_status(req, "409 Conflict");
      return httpd_resp_send(req, "Manual posing active; explicitly resume servos first", HTTPD_RESP_USE_STRLEN);
    }
    if (mode == "release" || mode == "resume") prefs.putBool("head_released", mode == "release");
    portENTER_CRITICAL(&headMux);
    if (mode == "release" || mode == "resume") {
      bool released = mode == "release";
      if (released != headReleased) headRestartAt = millis() + 200;
      headReleased = released;
    }
    headPan = pan; headTilt = tilt; headHold = mode != "absolute"; headReceived = millis();
    portEXIT_CRITICAL(&headMux);
  }
  JsonDocument output;
  if (servoPowerEnabled && servoPowerVerified && !headRestartAt) {
    output["yaw_deg"] = M5StackChan.Motion.getCurrentYawAngle() / 10.0f;
    output["pitch_deg"] = M5StackChan.Motion.getCurrentPitchAngle() / 10.0f;
  } else {
    output["yaw_deg"] = nullptr; output["pitch_deg"] = nullptr;
  }
  output["device_us"] = esp_timer_get_time();
  output["watchdog_ms"] = 300;
  output["control_mode"] = "absolute";
  output["command_mode"] = headReleased ? "release" : (headHold ? "hold" : "absolute");
  output["manual_posing"] = headReleased;
  output["release_applied"] = headReleased && headReleaseApplied && !headRestartAt;
  output["servo_power_enabled"] = servoPowerEnabled;
  output["servo_power_verified"] = servoPowerVerified;
  output["restarting"] = headRestartAt != 0;
  String encoded;
  serializeJson(output, encoded);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, encoded.c_str(), encoded.length());
}

void updateHead() {
  static uint32_t last = millis();
  uint32_t now = millis();
  if (now - last < 20) return;
  last = now;
  float pan, tilt;
  bool hold, released;
  uint32_t received;
  portENTER_CRITICAL(&headMux);
  pan = headPan; tilt = headTilt; hold = headHold; released = headReleased; received = headReceived;
  portEXIT_CRITICAL(&headMux);
  // Manual posing cuts the physical servo rail. Mode transitions reboot so
  // internal I2C is touched only before camera SCCB takes ownership of it.
  if (released || headRestartAt || !servoPowerEnabled || !servoPowerVerified) return;
  // A released stick is a position target (0, 0), not a stop command.
  // Explicit hold, lost input, or a network outage stops at the current pose.
  if (hold || now - received > 300) {
    if (headMoving) M5StackChan.Motion.stop();
    headMoving = false;
    return;
  }
  const float targetYaw = constrain(pan * 45.0f, -45.0f, 45.0f);
  const float targetPitch = constrain(tilt * 85.0f, 0.0f, 85.0f);
  if (!headMoving || fabsf(targetYaw - headYaw) >= 0.1f || fabsf(targetPitch - headPitch) >= 0.1f) {
    if (!headMoving) M5StackChan.Motion.setTorqueEnabled(true);
    headYaw = targetYaw;
    headPitch = targetPitch;
    M5StackChan.Motion.move(lroundf(headYaw * 10), lroundf(headPitch * 10), 400);
    headMoving = true;
  }
}

void reply(int id, const char* status) {
  JsonDocument out;
  out["id"] = id;
  out["status"] = status;
  out["firmware"] = "stackchan-camera";
  out["version"] = "0.6.7";
  out["ip"] = networkAddress();
  out["connected"] = networkReady();
  out["network_mode"] = directWifi ? "ap" : "station";
  out["ap_clients"] = directWifi ? WiFi.softAPgetStationNum() : 0;
  out["camera_ready"] = cameraReady;
  out["frames_sent"] = framesSent;
  out["frames_encoded"] = sequence;
  out["head_control_ready"] = headServer != nullptr;
  Serial.print("@stackchan "); serializeJson(out, Serial); Serial.println();
}

esp_err_t stream(httpd_req_t* req) {
  char provided[100] = {};
  httpd_req_get_hdr_value_str(req, "X-Stream-Key", provided, sizeof(provided));
  if (!streamKey.length() || streamKey != provided) {
    httpd_resp_set_status(req, "403 Forbidden");
    return httpd_resp_send(req, "Forbidden", HTTPD_RESP_USE_STRLEN);
  }
  // Multipart headers/chunk trailers are small writes: do not hold them for
  // Nagle aggregation and a receiver's delayed ACK timer.
  int noDelay = 1;
  int streamSocket = httpd_req_to_sockfd(req);
  setsockopt(streamSocket, IPPROTO_TCP, TCP_NODELAY, &noDelay, sizeof(noDelay));
  int actualNoDelay = -1;
  socklen_t optionSize = sizeof(actualNoDelay);
  getsockopt(streamSocket, IPPROTO_TCP, TCP_NODELAY, &actualNoDelay, &optionSize);
  portENTER_CRITICAL(&profileMux);
  streamNoDelay = actualNoDelay;
  portEXIT_CRITICAL(&profileMux);
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  uint32_t lastSequence = UINT32_MAX;
  uint32_t previousSendUs = 0;
  while (true) {
    // One streaming client is serviced by this HTTP task. Copies own their JPEG
    // buffer, so the producer never waits on a network write or frees active data.
    if (xSemaphoreTake(frameAvailable, pdMS_TO_TICKS(2000)) != pdTRUE) return ESP_FAIL;
    xSemaphoreTake(frameMutex, portMAX_DELAY);
    EncodedFrame frame = latestFrame;
    if (!frame.jpeg || frame.sequence == lastSequence) {
      xSemaphoreGive(frameMutex);
      continue;
    }
    constexpr size_t HEADER_RESERVE = 800;
    uint8_t* packet = (uint8_t*)malloc(frame.size + HEADER_RESERVE);
    if (packet) memcpy(packet + HEADER_RESERVE, frame.jpeg, frame.size);
    xSemaphoreGive(frameMutex);
    if (!packet) return ESP_ERR_NO_MEM;
    lastSequence = frame.sequence;
    size_t size = frame.size;
    uint64_t sensorUs = frame.sensorUs;
    uint32_t encodeUs = frame.encodeUs, captureWaitUs = frame.captureWaitUs;
    uint32_t missedSlots = frame.missedSlots;
    uint32_t disconnects, reason;
    portENTER_CRITICAL(&profileMux);
    disconnects = wifiDisconnects; reason = lastWifiReason;
    portEXIT_CRITICAL(&profileMux);
    char header[HEADER_RESERVE];
    uint64_t sentUs = esp_timer_get_time();
    char signalHeader[40] = {};
    if (!directWifi) snprintf(signalHeader, sizeof(signalHeader), "X-Rssi-Dbm: %d\r\n", WiFi.RSSI());
    int len = snprintf(header, sizeof(header),
      "\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\nX-Sequence: %u\r\nX-Sensor-Us: %llu\r\nX-Sent-Us: %llu\r\nX-Boot-Id: %u\r\nX-Width: 320\r\nX-Height: 240\r\nX-Jpeg-Quality: %u\r\nX-Target-Fps: %u\r\nX-Encode-Us: %u\r\nX-Capture-Wait-Us: %u\r\nX-Previous-Send-Us: %u\r\nX-Missed-Slots: %u\r\n%sX-Wifi-Disconnects: %u\r\nX-Last-Wifi-Reason: %u\r\nX-Tcp-No-Delay: %d\r\nX-Network-Mode: %s\r\nX-Firmware: 0.6.3\r\n\r\n",
      unsigned(size), frame.sequence, sensorUs, sentUs, bootId, frame.quality, frame.fps,
      encodeUs, captureWaitUs, previousSendUs, missedSlots, signalHeader, disconnects,
      reason, actualNoDelay, directWifi ? "ap" : "station");
    if (len <= 0 || size_t(len) >= HEADER_RESERVE) { free(packet); return ESP_FAIL; }
    // Send the multipart header and JPEG in one HTTP chunk. This avoids a
    // separate small write/ACK cycle ahead of each image, without extra copies
    // of the JPEG or any change to the multipart body read by existing clients.
    uint8_t* start = packet + HEADER_RESERVE - len;
    memcpy(start, header, len);
    esp_err_t result = httpd_resp_send_chunk(req, (const char*)start, len + size);
    previousSendUs = esp_timer_get_time() - sentUs;
    free(packet);
    if (result != ESP_OK) return result;
    framesSent++;
    delay(1);
  }
}

// Explicit bulk-transfer diagnostic, separate from images and recordings.
// The normal encoder remains running, so the test includes its CPU load.
esp_err_t throughput(httpd_req_t* req) {
  if (!authorized(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Forbidden");
  int noDelay = 1;
  setsockopt(httpd_req_to_sockfd(req), IPPROTO_TCP, TCP_NODELAY, &noDelay, sizeof(noDelay));
  static const uint8_t payload[16384] = {};
  httpd_resp_set_type(req, "application/octet-stream");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  for (int i = 0; i < 256; i++) {
    esp_err_t result = httpd_resp_send_chunk(req, (const char*)payload, sizeof(payload));
    if (result != ESP_OK) return result;
  }
  return httpd_resp_send_chunk(req, nullptr, 0);
}

void startCamera() {
  M5.Mic.end();
  startSpeech();
  M5StackChan.showRgbColor(0, 12, 8);
  // Camera SCCB owns pins 11/12 for the entire session. Do not call M5.update,
  // touch, power reads, LEDs, or speaker initialization after bus handover.
  // Already-initialized I2S playback does not access I2C.
  M5.In_I2C.release();
  cameraReady = esp_camera_init(&cameraConfig) == ESP_OK;
  if (!cameraReady) return;
  frameMutex = xSemaphoreCreateMutex();
  frameAvailable = xSemaphoreCreateBinary();
  if (!frameMutex || !frameAvailable ||
      xTaskCreate(captureFrames, "camera_capture", 8192, nullptr, 2, nullptr) != pdPASS) {
    cameraReady = false;
    return;
  }
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.stack_size = 8192;
  config.max_open_sockets = 2;
  config.send_wait_timeout = 2;
  if (httpd_start(&server, &config) != ESP_OK) return;
  httpd_uri_t endpoint = {};
  endpoint.uri = "/stream";
  endpoint.method = HTTP_GET;
  endpoint.handler = stream;
  httpd_register_uri_handler(server, &endpoint);
  httpd_uri_t speedEndpoint = {};
  speedEndpoint.uri = "/throughput";
  speedEndpoint.method = HTTP_GET;
  speedEndpoint.handler = throughput;
  httpd_register_uri_handler(server, &speedEndpoint);
  // Streaming owns its HTTP task indefinitely. Head commands need a separate
  // server/task, and use servo UART only, leaving the camera I2C bus alone.
  httpd_config_t headConfig = HTTPD_DEFAULT_CONFIG();
  headConfig.server_port = 81;
  headConfig.ctrl_port = 32769;
  headConfig.stack_size = 6144;
  headConfig.max_uri_handlers = 12;
  headConfig.recv_wait_timeout = 1;
  headConfig.send_wait_timeout = 1;
  if (httpd_start(&headServer, &headConfig) == ESP_OK) {
    httpd_uri_t headEndpoint = {};
    headEndpoint.uri = "/head";
    headEndpoint.method = HTTP_POST;
    headEndpoint.handler = headControl;
    httpd_register_uri_handler(headServer, &headEndpoint);
    httpd_uri_t profileEndpoint = {};
    profileEndpoint.uri = "/camera";
    profileEndpoint.method = HTTP_GET;
    profileEndpoint.handler = cameraProfile;
    httpd_register_uri_handler(headServer, &profileEndpoint);
    profileEndpoint.method = HTTP_POST;
    httpd_register_uri_handler(headServer, &profileEndpoint);
    headEndpoint.method = HTTP_GET;
    httpd_register_uri_handler(headServer, &headEndpoint);
    registerFaces(headServer);
    registerSpeech(headServer);
  }
}

void connectWifi() {
  // Initialize lwIP even on first boot without saved credentials: HTTP needs
  // its network mutexes while USB provisioning is still available.
  streamKey = prefs.getString("key", "");
  // Consume the one-shot flag before starting AP: reset/power-cycle always
  // returns to the saved home network, including a failed AP startup.
  bool startDirect = prefs.getBool("ap_once", false);
  prefs.remove("ap_once");
  if (startDirect) {
    String ssid = prefs.getString("ap_ssid", "");
    String password = prefs.getString("ap_password", "");
    uint32_t leaseSeconds = prefs.getUInt("ap_lease", 480);
    int channel = prefs.getUInt("ap_channel", 6);
    prefs.remove("ap_password");
    if (ssid.length() && password.length() >= 8 &&
        (leaseSeconds == 0 || (leaseSeconds >= 60 && leaseSeconds <= 900))) {
      WiFi.mode(WIFI_AP);
      WiFi.setSleep(false);
      IPAddress ip(192, 168, 4, 1);
      if (WiFi.softAPConfig(ip, ip, IPAddress(255, 255, 255, 0)) &&
          WiFi.softAP(ssid.c_str(), password.c_str(), channel, 0, 1)) {
        directWifi = true;
        directWifiStarted = millis();
        directWifiLeaseMs = leaseSeconds * 1000;
        return;
      }
    }
    WiFi.softAPdisconnect(true);
  }
  WiFi.mode(WIFI_STA);
  WiFi.onEvent([](WiFiEvent_t, WiFiEventInfo_t info) {
    portENTER_CRITICAL(&profileMux);
    wifiDisconnects++;
    lastWifiReason = info.wifi_sta_disconnected.reason;
    portEXIT_CRITICAL(&profileMux);
  }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  String ssid = prefs.getString("ssid", "");
  String password = prefs.getString("password", "");
  if (!ssid.length()) return;
  WiFi.setSleep(false);
  WiFi.begin(ssid.c_str(), password.c_str());
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) delay(100);
  if (WiFi.status() == WL_CONNECTED) {
    MDNS.begin("stackchan-drive");
    MDNS.addService("http", "tcp", 80);
  }
}

void setup() {
  bootId = esp_random();
  Serial.begin(921600);
  Serial.setTimeout(1000);
  M5StackChan.begin();
  M5StackChan.Motion.setAutoAngleSyncEnabled(false);
  M5StackChan.Motion.setAutoTorqueReleaseEnabled(false);
  prefs.begin("drive-camera", false);
  headReleased = prefs.getBool("head_released", true);
  M5StackChan.Motion.setTorqueEnabled(false);
  M5StackChan.setServoPowerEnabled(!headReleased);
  delay(20);
  // PY32 VM_EN is GPIO 0. Require successful readback, not just a sent write.
  uint8_t powerOutput = 0xFF, powerInput = 0xFF;
  servoPowerVerified = M5.In_I2C.readRegister(0x6F, 0x05, &powerOutput, 1, 100000) &&
    M5.In_I2C.readRegister(0x6F, 0x07, &powerInput, 1, 100000) &&
    bool(powerOutput & 1) == !headReleased;
  // VM_EN is configured as an output. Its input buffer need not mirror a
  // driven high level; GPIO_O is the authoritative output-latch readback.
  servoPowerEnabled = bool(powerOutput & 1);
  headReleaseApplied = headReleased && servoPowerVerified && !servoPowerEnabled;
  if (!headReleased && servoPowerVerified) {
    // Hold the current hand-posed position, without centering on restart.
    M5StackChan.Motion.setAutoAngleSyncEnabled(true);
    M5StackChan.Motion.stop();
    M5StackChan.Motion.setTorqueEnabled(true);
  }
  connectWifi();
  auto& display = M5StackChan.Display();
  display.fillScreen(TFT_BLACK);
  display.setTextColor(TFT_CYAN);
  display.setTextSize(2);
  display.setCursor(15, 35);
  display.println("STACK CHAN DRIVE");
  display.println(networkReady() ? networkAddress() : "USB Wi-Fi setup");
  startCamera();
  startFaces();
  reply(0, "ready");
}

void loop() {
  if (headRestartAt && int32_t(millis() - headRestartAt) >= 0) ESP.restart();
  updateHead();
  // Optional AP lease bounds offline experiments. With Ethernet, lease 0 keeps
  // direct Wi-Fi until reset or wifi_station; reset always returns to home Wi-Fi.
  if (directWifi && directWifiLeaseMs && millis() - directWifiStarted >= directWifiLeaseMs) ESP.restart();
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    JsonDocument request;
    if (!deserializeJson(request, line)) {
      int id = request["id"] | -1;
      String command = request["command"] | "";
      if (command == "wifi_config") {
        String ssid = request["ssid"] | "";
        String password = request["password"] | "";
        String key = request["key"] | "";
        if (ssid.length() > 0 && ssid.length() <= 32 && password.length() <= 63 && key.length() >= 24) {
          prefs.putString("ssid", ssid); prefs.putString("password", password); prefs.putString("key", key);
          reply(id, "saved");
          delay(100);
          ESP.restart();
        } else reply(id, "invalid_config");
      } else if (command == "wifi_ap") {
        String ssid = request["ssid"] | "";
        String password = request["password"] | "";
        int lease = request["lease_seconds"] | 480;
        int channel = request["channel"] | 6;
        if (streamKey.length() >= 24 && ssid.length() > 0 && ssid.length() <= 32 &&
            password.length() >= 8 && password.length() <= 63 &&
            (lease == 0 || (lease >= 60 && lease <= 900)) && channel >= 1 && channel <= 11) {
          prefs.putString("ap_ssid", ssid); prefs.putString("ap_password", password);
          prefs.putUInt("ap_lease", lease); prefs.putUInt("ap_channel", channel);
          prefs.putBool("ap_once", true);
          reply(id, "saved");
          delay(100);
          ESP.restart();
        } else reply(id, "invalid_config");
      } else if (command == "wifi_station") {
        prefs.remove("ap_once");
        reply(id, "saved");
        delay(100);
        ESP.restart();
      } else if (command == "ping" || command == "status") reply(id, "succeeded");
    }
  }
  delay(5);
}
