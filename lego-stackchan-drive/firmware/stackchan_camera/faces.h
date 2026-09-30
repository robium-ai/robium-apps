// LCD-only actions. No M5.update(), I2C, speaker playback, servo or camera calls here.
#pragma once
#include <esp_heap_caps.h>

const char* faceNames[] = {"neutral", "happy", "angry", "sad", "doubtful", "sleepy", "curious"};
struct FaceState {
  uint8_t emotion = 6;
  bool talking = false, autoCycle = false, animated = true;
  uint32_t changed = 0, rendered = 0, frames = 0, renderUs = 0;
  uint32_t revision = 0, renderedRevision = UINT32_MAX;
  uint8_t visible = 0;
};
FaceState faceState;
portMUX_TYPE faceMux = portMUX_INITIALIZER_UNLOCKED;
SemaphoreHandle_t faceCanvasMutex = nullptr;
M5Canvas faceCanvas(&M5StackChan.Display());
bool faceReady = false;

FaceState getFaceState() {
  portENTER_CRITICAL(&faceMux);
  FaceState state = faceState;
  portEXIT_CRITICAL(&faceMux);
  return state;
}

void drawSpectrum(int gy, const float* audioBands = nullptr) {
  // Twice the previous glyph width and peak height. The lower center keeps
  // the tallest bars clear of the eyes; all five remain visible while idle.
  const uint32_t bg = 0x080E19;
  faceCanvas.fillRect(116, 142, 88, 78, bg);
  const uint32_t colors[] = {0x738997, 0x8CA5B1, 0xABC4CD, 0xC5DEE6, 0xDFF9FF};
  for (size_t b = 0; b < speechBands; b++) {
    // Every band uses the same 12–72 px range. Position never biases height.
    int height = 12 + lroundf(audioBands ? audioBands[b] * 60 : 0);
    faceCanvas.fillRoundRect(128 + b * 14, 180 + gy - height / 2, 8, height, 4, colors[b]);
  }
}

void drawFace(uint8_t emotion, bool animated, uint32_t now, const float* audioBands = nullptr) {
  const uint32_t bg = 0x080E19, ink = 0xDFF9FF, pink = 0xEB749E;
  faceCanvas.fillScreen(bg);
  float t = animated ? now / 1000.0f : 0;
  int gx = animated ? lroundf(3 * sinf(t * .63f)) : 0;
  int gy = animated ? lroundf(2 * sinf(t * 1.2f)) : 0;
  // A 170 ms blink every ~4.7 s. Gaze moves pixels only, never the head.
  bool blink = animated && now % 4700 >= 4530;
  for (int side = 0; side < 2; side++) {
    int x = (side ? 216 : 104) + gx, y = 100 + gy;
    if (blink || emotion == 5) {
      faceCanvas.fillRoundRect(x - 28, y + 5, 56, 7, 3, ink);
    } else if (emotion == 6) {
      // Open, attentive eyes: slight asymmetry and a steady downward gaze.
      faceCanvas.fillRoundRect(x - 26, y - 34, 52, 70, 24, ink);
      faceCanvas.fillEllipse(x + (side ? -3 : 3), y + 10, 12, 18, bg);
      faceCanvas.fillCircle(x + (side ? -6 : 0), y + 3, 3, 0xFFFFFF);
      faceCanvas.fillRoundRect(x - 22, y - (side ? 48 : 52), 44, 5, 2, ink);
    } else if (emotion == 1) {
      faceCanvas.fillEllipse(x, y, 29, 28, ink);
      faceCanvas.fillEllipse(x, y + 17, 31, 27, bg);
    } else {
      int height = emotion == 4 && side == 0 ? 26 : 37;
      faceCanvas.fillRoundRect(x - 23, y - height, 46, height * 2, 20, ink);
      if (emotion == 2) {
        // Brows slope inward; trim the eye to follow the brow.
        if (!side) faceCanvas.fillTriangle(x - 29, y - 41, x + 29, y - 10,
                                          x + 29, y - 41, bg);
        else faceCanvas.fillTriangle(x - 29, y - 10, x + 29, y - 41,
                                     x - 29, y - 41, bg);
      } else if (emotion == 3) {
        if (!side) faceCanvas.fillTriangle(x - 28, y - 10, x + 28, y - 40,
                                          x - 28, y - 40, bg);
        else faceCanvas.fillTriangle(x - 28, y - 40, x + 28, y - 10,
                                     x + 28, y - 40, bg);
      }
      if (emotion == 4 && side == 1)
        faceCanvas.fillRoundRect(x - 26, y - 52, 52, 5, 2, ink);
    }
  }
  if (emotion == 1) {
    faceCanvas.fillEllipse(75 + gx, 139 + gy, 11, 5, pink);
    faceCanvas.fillEllipse(245 + gx, 139 + gy, 11, 5, pink);
  } else if (emotion == 5) {
    faceCanvas.setTextColor(0x6CB3BF, bg);
    faceCanvas.setTextSize(2);
    faceCanvas.setCursor(257, 40); faceCanvas.print("z");
    faceCanvas.setCursor(279, 24); faceCanvas.print("z");
  }
  drawSpectrum(gy, audioBands);
}

void renderFaces(void*) {
  const TickType_t period = pdMS_TO_TICKS(125); // 8 FPS leaves camera/HTTP headroom.
  TickType_t wake = xTaskGetTickCount();
  uint8_t lastEmotion = UINT8_MAX;
  uint32_t lastFull = 0, lastRevision = UINT32_MAX;
  bool wasSpeaking = false;
  bool lastBlink = false;
  int gazeY = 0;
  while (true) {
    uint32_t now = millis();
    FaceState state = getFaceState();
    SpeechState speech = getSpeechState();
    const TickType_t tick = speech.active ? pdMS_TO_TICKS(50) : period;
    if (!speech.active && !wasSpeaking && !state.animated && !state.autoCycle && state.revision == state.renderedRevision) {
      vTaskDelayUntil(&wake, period);
      continue;
    }
    uint8_t emotion = state.autoCycle ? ((now - state.changed) / 4000) % 7 : state.emotion;
    uint64_t start = esp_timer_get_time();
    xSemaphoreTake(faceCanvasMutex, portMAX_DELAY);
    // Full PSRAM canvas drawing is costly while JPEG encoding runs. Keep
    // gaze gentle during speech and spend the remaining ticks on its mouth.
    bool blink = state.animated && now % 4700 >= 4530;
    bool full = now - lastFull >= (speech.active ? 500 : 125) || blink != lastBlink || emotion != lastEmotion ||
      state.revision != lastRevision || speech.active != wasSpeaking;
    if (full) {
      lastFull = now; lastBlink = blink;
      gazeY = state.animated ? lroundf(2 * sinf(now / 1000.0f * 1.2f)) : 0;
      drawFace(emotion, state.animated, now, speech.active ? speech.bands : nullptr);
    } else drawSpectrum(gazeY, speech.active ? speech.bands : nullptr);
    // Clear the boot screen once, then send only regions that faces can change.
    // Include the sleepy decoration when switching expressions/talking so it
    // cannot remain on the physical LCD after disappearing from the canvas.
    auto& display = M5StackChan.Display();
    if (lastEmotion != UINT8_MAX) {
      if (full) display.setClipRect(56, 40, 208, 180);
      else display.setClipRect(116, 142, 88, 78);
    }
    faceCanvas.pushSprite(0, 0);
    if (full && lastEmotion != UINT8_MAX && (emotion != lastEmotion || emotion == 5)) {
      display.setClipRect(250, 18, 64, 48);
      faceCanvas.pushSprite(0, 0);
    }
    display.clearClipRect();
    lastEmotion = emotion; lastRevision = state.revision; wasSpeaking = speech.active;
    xSemaphoreGive(faceCanvasMutex);
    noteSpeechFrame(speech);
    uint32_t elapsed = esp_timer_get_time() - start;
    portENTER_CRITICAL(&faceMux);
    faceState.visible = emotion;
    faceState.rendered = millis();
    faceState.renderedRevision = state.revision;
    faceState.frames++;
    faceState.renderUs = elapsed;
    portEXIT_CRITICAL(&faceMux);
    // Do not catch up by doing back-to-back redraws after a slow snapshot/draw.
    if (xTaskGetTickCount() - wake >= tick) wake = xTaskGetTickCount();
    vTaskDelayUntil(&wake, tick);
  }
}

void startFaces() {
  faceCanvasMutex = xSemaphoreCreateMutex();
  faceCanvas.setPsram(true);
  faceCanvas.setColorDepth(16);
  if (!faceCanvasMutex || !faceCanvas.createSprite(320, 240)) return;
  faceState.changed = millis();
  faceReady = xTaskCreate(renderFaces, "lcd_face", 4096, nullptr, 1, nullptr) == pdPASS;
}

esp_err_t faceUnavailable(httpd_req_t* req, const char* reason) {
  httpd_resp_set_status(req, "503 Service Unavailable");
  return httpd_resp_send(req, reason, HTTPD_RESP_USE_STRLEN);
}

esp_err_t faceControl(httpd_req_t* req) {
  if (!authorized(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Forbidden");
  if (!faceReady) return faceUnavailable(req, "Face renderer unavailable");
  if (req->method == HTTP_POST) {
    if (req->content_len <= 0 || req->content_len > 200)
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid face command length");
    char body[201] = {};
    int received = 0;
    while (received < req->content_len) {
      int count = httpd_req_recv(req, body + received, req->content_len - received);
      if (count <= 0) return ESP_FAIL;
      received += count;
    }
    JsonDocument input;
    if (deserializeJson(input, body) || !input.is<JsonObject>() || input.size() == 0)
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected a face object");
    int emotion = -1;
    for (JsonPair pair : input.as<JsonObject>()) {
      String key = pair.key().c_str();
      if (key == "emotion") {
        if (pair.value().is<const char*>())
          for (int i = 0; i < 7; i++) if (pair.value().as<String>() == faceNames[i]) emotion = i;
        if (emotion < 0) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Unknown emotion");
      } else if ((key != "talking" && key != "auto_cycle" && key != "animated") || !pair.value().is<bool>()) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Unknown field or invalid boolean");
      }
    }
    // Validate every field before applying any part of the action.
    portENTER_CRITICAL(&faceMux);
    if (emotion >= 0) { faceState.emotion = emotion; faceState.autoCycle = false; }
    if (input["talking"].is<bool>()) faceState.talking = input["talking"].as<bool>();
    if (input["auto_cycle"].is<bool>()) faceState.autoCycle = input["auto_cycle"].as<bool>();
    if (input["animated"].is<bool>()) faceState.animated = input["animated"].as<bool>();
    faceState.changed = millis();
    faceState.revision++;
    portEXIT_CRITICAL(&faceMux);
  }
  FaceState state = getFaceState();
  JsonDocument out;
  out["emotion"] = faceNames[state.emotion];
  out["visible_emotion"] = faceNames[state.visible];
  out["talking"] = state.talking;
  out["auto_cycle"] = state.autoCycle;
  out["animated"] = state.animated;
  out["renderer_ready"] = faceReady;
  out["frames_rendered"] = state.frames;
  out["last_render_ms"] = state.rendered;
  out["last_render_us"] = state.renderUs;
  out["revision"] = state.revision;
  out["rendered_revision"] = state.renderedRevision;
  out["target_render_fps"] = getSpeechState().active ? 20.0f : 8.0f;
  out["audio_driven"] = getSpeechState().active;
  out["speech_visual"] = "mouth_spectrum";
  out["spectrum_always_visible"] = true;
  out["firmware"] = "0.6.7";
  out["boot_id"] = bootId;
  String encoded;
  serializeJson(out, encoded);
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  return httpd_resp_send(req, encoded.c_str(), encoded.length());
}

void bmpInt(uint8_t* data, uint32_t value) {
  for (int i = 0; i < 4; i++) data[i] = (value >> (8 * i)) & 255;
}

esp_err_t faceSnapshot(httpd_req_t* req) {
  if (!authorized(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Forbidden");
  if (!faceReady) return faceUnavailable(req, "Face renderer unavailable");
  const size_t size = 54 + 320 * 240 * 3;
  uint8_t* bmp = (uint8_t*)heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!bmp) return faceUnavailable(req, "Snapshot memory unavailable");
  memset(bmp, 0, 54);
  bmp[0] = 'B'; bmp[1] = 'M';
  bmpInt(bmp + 2, size); bmpInt(bmp + 10, 54); bmpInt(bmp + 14, 40);
  bmpInt(bmp + 18, 320); bmpInt(bmp + 22, uint32_t(-240)); // Top-down, BGR24.
  bmp[26] = 1; bmp[28] = 24;
  bmpInt(bmp + 34, size - 54);
  xSemaphoreTake(faceCanvasMutex, portMAX_DELAY);
  // rgb888_t stores B,G,R bytes; readRectRGB(uint8_t*) instead stores R,G,B.
  // The typed conversion gives BMP order directly without a second PSRAM pass.
  faceCanvas.readRect(0, 0, 320, 240, (lgfx::rgb888_t*)(bmp + 54));
  xSemaphoreGive(faceCanvasMutex);
  // A slow snapshot receiver never holds the rendering mutex.
  httpd_resp_set_type(req, "image/bmp");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t result = httpd_resp_send(req, (const char*)bmp, size);
  free(bmp);
  return result;
}

void registerFaces(httpd_handle_t controlServer) {
  httpd_uri_t endpoint = {};
  endpoint.uri = "/face";
  endpoint.handler = faceControl;
  endpoint.method = HTTP_GET;
  httpd_register_uri_handler(controlServer, &endpoint);
  endpoint.method = HTTP_POST;
  httpd_register_uri_handler(controlServer, &endpoint);
  endpoint.uri = "/face.bmp";
  endpoint.handler = faceSnapshot;
  endpoint.method = HTTP_GET;
  httpd_register_uri_handler(controlServer, &endpoint);
}
