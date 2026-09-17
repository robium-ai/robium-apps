/*
 * Minimal USB companion firmware for M5Stack STACK-CHAN K151.
 * SPDX-License-Identifier: MIT
 */
#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5StackChan.h>
#include <driver/uart.h>
#include <esp_camera.h>
#include <esp_heap_caps.h>
#include <img_converters.h>

namespace {
constexpr uint32_t kBaud = 921600;
constexpr uint32_t kSampleRate = 16000;
constexpr size_t kMaxAudioBytes = kSampleRate * 2 * 40;
constexpr size_t kAudioChunkBytes = 240;
constexpr size_t kMaxImageBytes = 512000;
constexpr int kMinYaw = -45;
constexpr int kMaxYaw = 45;
constexpr int kMinPitch = 5;
constexpr int kMaxPitch = 85;
constexpr int kMinSpeed = 100;
constexpr int kMaxSpeed = 400;
constexpr int kAnimationSpeed = 850;
constexpr int kHalfTurnVelocity = 650;
constexpr uint32_t kHalfTurnDurationMs = 650;
bool cameraInitialized = false;
bool facingBack = false;

camera_config_t cameraConfig = {
    .pin_pwdn = -1,
    .pin_reset = -1,
    .pin_xclk = -1,
    .pin_sccb_sda = 12,
    .pin_sccb_scl = 11,
    .pin_d7 = 47,
    .pin_d6 = 48,
    .pin_d5 = 16,
    .pin_d4 = 15,
    .pin_d3 = 42,
    .pin_d2 = 41,
    .pin_d1 = 40,
    .pin_d0 = 39,
    .pin_vsync = 46,
    .pin_href = 38,
    .pin_pclk = 45,
    .xclk_freq_hz = 20000000,
    .ledc_timer = LEDC_TIMER_0,
    .ledc_channel = LEDC_CHANNEL_0,
    .pixel_format = PIXFORMAT_RGB565,
    .frame_size = FRAMESIZE_QVGA,
    .jpeg_quality = 0,
    .fb_count = 2,
    .fb_location = CAMERA_FB_IN_PSRAM,
    .grab_mode = CAMERA_GRAB_LATEST,
    .sccb_i2c_port = -1,
};

void sendJson(JsonDocument& response) {
  Serial.print("@stackchan ");
  serializeJson(response, Serial);
  Serial.print('\n');
  Serial.flush();
}

void sendError(int id, const char* message) {
  JsonDocument response;
  response["id"] = id;
  response["status"] = "error";
  response["error"] = message;
  sendJson(response);
}

void drawText(const String& text, uint16_t accent = TFT_CYAN) {
  auto& display = M5StackChan.Display();
  display.startWrite();
  display.fillScreen(TFT_BLACK);
  display.fillCircle(86, 70, 24, TFT_WHITE);
  display.fillCircle(234, 70, 24, TFT_WHITE);
  display.fillCircle(86, 70, 10, accent);
  display.fillCircle(234, 70, 10, accent);
  display.drawRoundRect(12, 120, display.width() - 24, display.height() - 132, 12, accent);
  display.setTextColor(TFT_WHITE, TFT_BLACK);
  display.setTextDatum(top_left);
  display.setTextSize(2);
  display.setTextWrap(true, true);
  display.setCursor(24, 134);
  display.print(text);
  display.endWrite();
}

void waitForMotion() {
  const uint32_t deadline = millis() + 5000;
  while (M5StackChan.Motion.isMoving() && millis() < deadline) {
    M5StackChan.update();
    delay(5);
  }
}

void restoreYawPositionMode() {
  // The SCS0009 enters continuous/PWM mode by storing zero angle limits in
  // the servo itself. Those registers survive an ESP32 reset, while the BSP's
  // in-memory mode cache does not. Restore the K151 yaw position range with a
  // single protocol write so a reset can always recover to the forward pose.
  uint8_t packet[] = {
      0xff, 0xff,  // header
      0x01,        // yaw servo id
      0x07,        // instruction + address + four data bytes + checksum
      0x03,        // write instruction
      0x09,        // minimum-angle register
      0x00, 0x00,  // minimum raw position: 0
      0x03, 0xe8,  // maximum raw position: 1000
      0x00,        // checksum; payload sum is 0xff
  };
  uart_flush_input(UART_NUM_1);
  uart_write_bytes(UART_NUM_1, packet, sizeof(packet));
  uart_wait_tx_done(UART_NUM_1, pdMS_TO_TICKS(100));
  delay(20);
  uart_flush_input(UART_NUM_1);
}

void movePose(int yaw, int pitch, int speed = kAnimationSpeed) {
  M5StackChan.Motion.move(yaw * 10, pitch * 10, speed);
  waitForMotion();
}

void movePitch(int pitch, int speed = kAnimationSpeed) {
  M5StackChan.Motion.movePitch(pitch * 10, speed);
  waitForMotion();
}

void stopContinuousYaw() {
  // Keep yaw in continuous-rotation mode at zero output. Motion.stop() switches
  // back to bounded position mode, which would pull a rear-facing head forward.
  M5StackChan.Motion.rotateYaw(0);
  delay(60);
}

void rotateHalfTurn(int velocity) {
  M5StackChan.Motion.rotateYaw(velocity);
  const uint32_t deadline = millis() + kHalfTurnDurationMs;
  while (millis() < deadline) {
    M5StackChan.update();
    delay(5);
  }
  stopContinuousYaw();
}

void handlePing(int id) {
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  response["firmware"] = "stackchan-er2";
  response["version"] = "0.4.0";
  sendJson(response);
}

void addState(JsonDocument& response) {
  response["yaw"] = M5StackChan.Motion.getCurrentYawAngle() / 10;
  response["pitch"] = M5StackChan.Motion.getCurrentPitchAngle() / 10;
  response["battery_voltage"] = M5StackChan.getBatteryVoltage();
  response["psram_bytes"] = ESP.getPsramSize();
  response["free_psram_bytes"] = ESP.getFreePsram();
  response["board"] = static_cast<int>(M5.getBoard());
  response["mic_enabled"] = M5.Mic.isEnabled();
  response["mic_running"] = M5.Mic.isRunning();
  response["speaker_enabled"] = M5.Speaker.isEnabled();
  response["camera_initialized"] = cameraInitialized;
  response["facing_back"] = facingBack;
}

void handleStatus(int id) {
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  addState(response);
  sendJson(response);
}

void handleMoveHead(int id, JsonDocument& request) {
  const int yaw = request["yaw"] | 9999;
  const int pitch = request["pitch"] | 9999;
  const int speed = request["speed"] | 150;
  if (yaw < kMinYaw || yaw > kMaxYaw || pitch < kMinPitch || pitch > kMaxPitch ||
      speed < kMinSpeed || speed > kMaxSpeed) {
    sendError(id, "head command outside conversational limits");
    return;
  }
  if (facingBack) {
    rotateHalfTurn(kHalfTurnVelocity);
    facingBack = false;
  }
  M5StackChan.Motion.move(yaw * 10, pitch * 10, speed);
  waitForMotion();
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  addState(response);
  sendJson(response);
}

void handleAnimate(int id, JsonDocument& request) {
  const char* animation = request["animation"] | "";

  if (strcmp(animation, "nod_yes") == 0) {
    // Pitch-only movement also works while yaw is parked facing backward.
    movePitch(45);
    movePitch(22);
    movePitch(68);
    movePitch(22);
    movePitch(45);
  } else if (strcmp(animation, "shake_no") == 0) {
    if (facingBack) {
      // Oscillate in continuous mode so a rear-facing head is not pulled into
      // the bounded positional range.
      M5StackChan.Motion.rotateYaw(-450);
      delay(120);
      M5StackChan.Motion.rotateYaw(450);
      delay(240);
      M5StackChan.Motion.rotateYaw(-450);
      delay(240);
      M5StackChan.Motion.rotateYaw(450);
      delay(120);
      stopContinuousYaw();
    } else {
      movePose(0, 45);
      movePose(-32, 45);
      movePose(32, 45);
      movePose(-32, 45);
      movePose(32, 45);
      movePose(0, 45);
    }
  } else if (strcmp(animation, "privacy") == 0) {
    // The K151 pitch axis is specified for 0..90 degrees. This named action
    // intentionally reaches the requested upper endpoint; generic movement
    // remains limited to 5..85 degrees.
    movePitch(90, 500);
  } else if (strcmp(animation, "turn_back") == 0) {
    if (!facingBack) {
      movePose(0, 45, 500);
      rotateHalfTurn(-kHalfTurnVelocity);
      facingBack = true;
    }
  } else if (strcmp(animation, "look_straight") == 0) {
    if (facingBack) {
      rotateHalfTurn(kHalfTurnVelocity);
      facingBack = false;
    }
    // A prior firmware session may have left the physical servo in PWM mode.
    // Explicitly enter that mode before asking movePose to switch back to
    // position mode; this keeps a USB reconnect recoverable.
    stopContinuousYaw();
    movePose(0, 45, 500);
  } else {
    sendError(id, "unknown animation");
    return;
  }

  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  response["animation"] = animation;
  addState(response);
  sendJson(response);
}

void handleShowText(int id, JsonDocument& request) {
  const char* value = request["text"] | "";
  String text(value);
  if (text.length() == 0 || text.length() > 720) {
    sendError(id, "text is empty or too long");
    return;
  }
  drawText(text);
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  sendJson(response);
}

void handleSpeak(int id, JsonDocument& request) {
  const size_t audioBytes = request["audio_bytes"] | 0;
  const uint32_t sampleRate = request["sample_rate"] | 0;
  if (audioBytes == 0 || audioBytes > kMaxAudioBytes || audioBytes % 2 ||
      sampleRate < 8000 || sampleRate > 48000) {
    sendError(id, "invalid PCM audio metadata");
    return;
  }
  M5.Mic.end();
  M5StackChan.showRgbColor(0, 0, 0);
  auto* audio = static_cast<int16_t*>(
      heap_caps_malloc(audioBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (audio == nullptr) {
    sendError(id, "could not allocate speech buffer");
    return;
  }
  JsonDocument ready;
  ready["id"] = id;
  ready["status"] = "ready";
  ready["chunk_bytes"] = kAudioChunkBytes;
  sendJson(ready);
  size_t received = 0;
  auto* bytes = reinterpret_cast<uint8_t*>(audio);
  while (received < audioBytes) {
    const size_t target = min(kAudioChunkBytes, audioBytes - received);
    size_t chunkReceived = 0;
    const uint32_t deadline = millis() + 3000;
    while (chunkReceived < target && millis() < deadline) {
      const size_t available = Serial.available();
      if (available > 0) {
        const size_t remaining = target - chunkReceived;
        const size_t countWanted = available < remaining ? available : remaining;
        const int count = Serial.read(bytes + received + chunkReceived, countWanted);
        if (count > 0) {
          chunkReceived += static_cast<size_t>(count);
        }
      } else {
        delay(1);
      }
    }
    received += chunkReceived;
    if (chunkReceived != target) {
      heap_caps_free(audio);
      char error[96];
      snprintf(error, sizeof(error), "speech payload timed out (%u/%u bytes)",
               static_cast<unsigned>(received), static_cast<unsigned>(audioBytes));
      sendError(id, error);
      return;
    }
    if (received < audioBytes) {
      JsonDocument progress;
      progress["id"] = id;
      progress["status"] = "continue";
      progress["received_bytes"] = received;
      sendJson(progress);
    }
  }
  M5.Speaker.begin();
  M5.Speaker.setVolume(180);
  if (!M5.Speaker.playRaw(audio, audioBytes / 2, sampleRate, false, 1, 0, true)) {
    heap_caps_free(audio);
    sendError(id, "speaker rejected PCM audio");
    return;
  }
  while (M5.Speaker.isPlaying()) {
    M5StackChan.update();
    delay(2);
  }
  heap_caps_free(audio);
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  response["audio_bytes"] = audioBytes;
  sendJson(response);
}

void handleRecord(int id, JsonDocument& request, bool continuous) {
  const uint32_t durationMs = request["duration_ms"] | 0;
  const uint32_t sampleRate = request["sample_rate"] | 0;
  const uint32_t minimumDurationMs = continuous ? 100 : 250;
  if (durationMs < minimumDurationMs || durationMs > 8000 || sampleRate != kSampleRate) {
    sendError(id, "invalid recording request");
    return;
  }
  const size_t sampleCount = static_cast<size_t>(sampleRate) * durationMs / 1000;
  const size_t audioBytes = sampleCount * sizeof(int16_t);
  auto* audio = static_cast<int16_t*>(
      heap_caps_malloc(audioBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (audio == nullptr) {
    sendError(id, "could not allocate microphone buffer");
    return;
  }
  M5.Speaker.end();
  const bool wasRunning = M5.Mic.isRunning();
  M5.Mic.begin();
  if (continuous) {
    if (!wasRunning) {
      M5StackChan.showRgbColor(0, 24, 0);
    }
  } else {
    drawText("Listening...", TFT_GREEN);
  }
  if (!M5.Mic.record(audio, sampleCount, sampleRate, false)) {
    heap_caps_free(audio);
    sendError(id, "microphone rejected recording buffer");
    return;
  }
  while (M5.Mic.isRecording()) {
    M5StackChan.update();
    delay(2);
  }
  if (!continuous) {
    M5.Mic.end();
  }
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  response["audio_bytes"] = audioBytes;
  response["sample_rate"] = sampleRate;
  sendJson(response);
  Serial.write(reinterpret_cast<uint8_t*>(audio), audioBytes);
  Serial.flush();
  heap_caps_free(audio);
  if (!continuous) {
    drawText("Thinking...", TFT_YELLOW);
  }
}

void handleStopListening(int id) {
  M5.Mic.end();
  M5StackChan.showRgbColor(0, 0, 0);
  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  sendJson(response);
}

bool beginCamera() {
  if (cameraInitialized) {
    return true;
  }
  M5.In_I2C.release();
  if (esp_camera_init(&cameraConfig) != ESP_OK) {
    return false;
  }
  cameraInitialized = true;
  return true;
}

void endCamera() {
  if (cameraInitialized) {
    esp_camera_deinit();
    cameraInitialized = false;
  }
  // The GC0308 SCCB bus shares pins 11/12 with STACK-CHAN's touch, RGB,
  // power, and audio devices. Restore M5Unified's internal I2C owner before
  // touching any of those peripherals again.
  M5.In_I2C.begin();
  delay(10);
}

void handleCaptureImage(int id) {
  M5.Mic.end();
  M5StackChan.showRgbColor(24, 12, 0);
  if (!beginCamera()) {
    endCamera();
    M5StackChan.showRgbColor(0, 0, 0);
    sendError(id, "camera initialization failed");
    return;
  }

  // Discard the first frame after a quiet period so exposure can settle.
  camera_fb_t* frame = esp_camera_fb_get();
  if (frame != nullptr) {
    esp_camera_fb_return(frame);
  }
  delay(40);
  frame = esp_camera_fb_get();
  if (frame == nullptr) {
    endCamera();
    M5StackChan.showRgbColor(0, 0, 0);
    sendError(id, "camera capture failed");
    return;
  }

  uint8_t* jpeg = nullptr;
  size_t jpegBytes = 0;
  const bool converted = frame2jpg(frame, 80, &jpeg, &jpegBytes);
  const size_t width = frame->width;
  const size_t height = frame->height;
  esp_camera_fb_return(frame);
  if (!converted || jpeg == nullptr || jpegBytes < 4 || jpegBytes > kMaxImageBytes) {
    free(jpeg);
    endCamera();
    M5StackChan.showRgbColor(0, 0, 0);
    sendError(id, "camera JPEG conversion failed");
    return;
  }

  endCamera();
  M5StackChan.showRgbColor(0, 0, 0);

  JsonDocument response;
  response["id"] = id;
  response["status"] = "succeeded";
  response["mime_type"] = "image/jpeg";
  response["image_bytes"] = jpegBytes;
  response["width"] = width;
  response["height"] = height;
  sendJson(response);
  Serial.write(jpeg, jpegBytes);
  Serial.flush();
  free(jpeg);
}

void handleRequest(const String& line) {
  JsonDocument request;
  const auto error = deserializeJson(request, line);
  if (error) {
    sendError(-1, "invalid JSON request");
    return;
  }
  const int id = request["id"] | -1;
  const char* command = request["command"] | "";
  if (id < 0) {
    sendError(id, "request id is required");
  } else if (strcmp(command, "ping") == 0) {
    handlePing(id);
  } else if (strcmp(command, "status") == 0) {
    handleStatus(id);
  } else if (strcmp(command, "move_head") == 0) {
    handleMoveHead(id, request);
  } else if (strcmp(command, "animate") == 0) {
    handleAnimate(id, request);
  } else if (strcmp(command, "show_text") == 0) {
    handleShowText(id, request);
  } else if (strcmp(command, "speak_pcm") == 0) {
    handleSpeak(id, request);
  } else if (strcmp(command, "record_audio") == 0) {
    handleRecord(id, request, false);
  } else if (strcmp(command, "listen_chunk") == 0) {
    handleRecord(id, request, true);
  } else if (strcmp(command, "stop_listening") == 0) {
    handleStopListening(id);
  } else if (strcmp(command, "capture_image") == 0) {
    handleCaptureImage(id);
  } else {
    sendError(id, "unknown command");
  }
}
}  // namespace

void setup() {
  Serial.begin(kBaud);
  Serial.setTimeout(25000);
  M5StackChan.begin();
  M5StackChan.Motion.setAutoAngleSyncEnabled(true);
  restoreYawPositionMode();
  movePose(0, 45, 500);
  facingBack = false;
  M5.Speaker.setVolume(180);
  drawText("STACK-CHAN ER2\nReady", TFT_CYAN);
  delay(100);
}

void loop() {
  M5StackChan.update();
  if (Serial.available()) {
    const String line = Serial.readStringUntil('\n');
    if (line.length() > 0) {
      handleRequest(line);
    }
  }
  delay(2);
}
