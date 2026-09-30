// Fixed 24 kHz mono S16LE clips. Initialize the amplifier before camera I2C;
// thereafter use the already-running I2S driver, never speaker begin/end/update.
#pragma once
#include <esp_heap_caps.h>

constexpr uint32_t speechRate = 24000, speechWindowSamples = 600;
constexpr size_t maxSpeechBytes = speechRate * 2 * 20;
constexpr size_t speechBands = 5;
struct SpeechEnvelope { uint16_t rms, bands[speechBands]; };
struct SpeechState {
  bool ready = false, busy = false, active = false;
  uint32_t clipId = 0, durationMs = 0, positionMs = 0;
  uint64_t startedUs = 0;
  float mouth = 0, displayedMouth = 0;
  float bands[speechBands] = {}, displayedBands[speechBands] = {};
  const char* phase = "unavailable";
  const char* error = "";
  uint32_t renderedFrames = 0, silentFrames = 0, voicedFrames = 0;
};
SpeechState speechState;
portMUX_TYPE speechMux = portMUX_INITIALIZER_UNLOCKED;
int16_t* speechPcm = nullptr;
size_t speechSampleCount = 0;
SemaphoreHandle_t speechAvailable = nullptr;

SpeechState getSpeechState() {
  portENTER_CRITICAL(&speechMux);
  SpeechState state = speechState;
  portEXIT_CRITICAL(&speechMux);
  return state;
}

void noteSpeechFrame(const SpeechState& state) {
  if (!state.active) return;
  portENTER_CRITICAL(&speechMux);
  if (speechState.active && state.clipId == speechState.clipId) {
    speechState.displayedMouth = state.mouth;
    memcpy(speechState.displayedBands, state.bands, sizeof(state.bands));
    speechState.renderedFrames++;
    if (state.mouth <= .02f) speechState.silentFrames++;
    else speechState.voicedFrames++;
  }
  portEXIT_CRITICAL(&speechMux);
}

void speechError(const char* error) {
  portENTER_CRITICAL(&speechMux);
  speechState.busy = speechState.active = false;
  speechState.mouth = speechState.displayedMouth = 0;
  memset(speechState.bands, 0, sizeof(speechState.bands));
  memset(speechState.displayedBands, 0, sizeof(speechState.displayedBands));
  speechState.phase = "error"; speechState.error = error;
  portEXIT_CRITICAL(&speechMux);
}

void playSpeech(void*) {
  while (true) {
    xSemaphoreTake(speechAvailable, portMAX_DELAY);
    int16_t* pcm = speechPcm;
    size_t samples = speechSampleCount;
    const size_t windows = (samples + speechWindowSamples - 1) / speechWindowSamples;
    SpeechEnvelope* envelope = (SpeechEnvelope*)heap_caps_malloc(windows * sizeof(SpeechEnvelope), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!envelope) { free(pcm); speechError("Envelope memory unavailable"); continue; }
    float peak = 0, spectralPeak = 0;
    // A lightweight overlapping filter bank gives broad low-to-high energy
    // bands, not FFT bins. Analyze the same PCM ahead of playback, never I2C.
    const float boundaries[] = {200, 500, 1200, 3000};
    float alpha[4], lowpass[4] = {}, bandPeak[speechBands] = {};
    for (size_t b = 0; b < 4; b++) alpha[b] = 1 - expf(-2 * PI * boundaries[b] / speechRate);
    for (size_t w = 0; w < windows; w++) {
      uint64_t sum = 0;
      float bandSum[speechBands] = {};
      size_t from = w * speechWindowSamples, to = min<size_t>(samples, from + speechWindowSamples);
      for (size_t i = from; i < to; i++) {
        int32_t value = pcm[i];
        sum += int64_t(value) * value;
        float sample = value / 32768.0f, previous = 0;
        for (size_t b = 0; b < 4; b++) {
          lowpass[b] += alpha[b] * (sample - lowpass[b]);
          float band = lowpass[b] - previous;
          bandSum[b] += band * band;
          previous = lowpass[b];
        }
        float high = sample - previous;
        bandSum[4] += high * high;
      }
      float rms = sqrtf(float(sum) / (to - from)) / 32768.0f;
      envelope[w].rms = lroundf(rms * 65535);
      peak = max(peak, rms);
      for (size_t b = 0; b < speechBands; b++) {
        float energy = sqrtf(bandSum[b] / (to - from));
        envelope[w].bands[b] = lroundf(constrain(energy, 0.0f, 1.0f) * 65535);
        bandPeak[b] = max(bandPeak[b], energy);
        spectralPeak = max(spectralPeak, energy);
      }
      if (w % 16 == 15) delay(1);
    }
    // A small DMA ring bounds audio/LCD scheduling offset (~21 ms). The
    // public M5 API has no DAC playhead: this is a scheduled PCM clock, not
    // measured sample feedback. Wait for the tail as well as isPlaying().
    constexpr uint32_t dmaUs = 128 * 4 * 1000000 / speechRate;
    uint64_t started = esp_timer_get_time();
    bool ok = M5.Speaker.isRunning() &&
      M5.Speaker.playRaw(pcm, samples, speechRate, false, 1, 0, true);
    if (!ok) {
      free(envelope); free(pcm); speechError("Speaker rejected audio"); continue;
    }
    started += dmaUs;
    uint64_t durationUs = uint64_t(samples) * 1000000 / speechRate;
    portENTER_CRITICAL(&speechMux);
    speechState.startedUs = started;
    speechState.active = true; speechState.phase = "playing";
    portEXIT_CRITICAL(&speechMux);
    float opening = 0;
    float bars[speechBands] = {};
    while (true) {
      uint64_t now = esp_timer_get_time();
      uint64_t position = now > started ? now - started : 0;
      if (position >= durationUs && !M5.Speaker.isPlaying(0)) break;
      if (position > durationUs + 2000000) {
        ok = false; M5.Speaker.stop(0);
        uint32_t deadline = millis() + 200;
        while (M5.Speaker.isPlaying(0) && millis() < deadline) delay(1);
        break;
      }
      size_t window = position / 25000;
      float rms = position < durationUs && now >= started && window < windows
        ? envelope[window].rms / 65535.0f : 0;
      float gate = max(.008f, peak * .08f);
      float target = rms > gate ? constrain((rms - gate) / max(.015f, peak * .65f - gate), 0.0f, 1.0f) : 0;
      // Fast opening, gentler closing; silence reaches an exactly closed mouth.
      opening = target > opening ? target : max(target, opening - .2f);
      if (opening < .02f) opening = 0;
      for (size_t b = 0; b < speechBands; b++) {
        float energy = position < durationUs && now >= started && window < windows
          ? envelope[window].bands[b] / 65535.0f : 0;
        float floor = max(.0015f, bandPeak[b] * .08f);
        float level = rms > gate && energy > floor
          ? constrain((energy - floor) / max(.005f, spectralPeak * .75f - floor), 0.0f, 1.0f) : 0;
        bars[b] += (level - bars[b]) * (level > bars[b] ? .7f : .25f);
        if (bars[b] < .02f) bars[b] = 0;
      }
      portENTER_CRITICAL(&speechMux);
      speechState.mouth = opening;
      memcpy(speechState.bands, bars, sizeof(bars));
      speechState.positionMs = min(uint64_t(speechState.durationMs), position / 1000);
      portEXIT_CRITICAL(&speechMux);
      delay(10);
    }
    free(envelope);
    bool drained = !M5.Speaker.isPlaying(0);
    if (drained) free(pcm);
    // A wedged driver may still own the source: retain it and refuse new
    // speech until restart, rather than free memory that I2S could still read.
    portENTER_CRITICAL(&speechMux);
    speechState.busy = speechState.active = false;
    speechState.mouth = speechState.displayedMouth = 0;
    memset(speechState.bands, 0, sizeof(speechState.bands));
    memset(speechState.displayedBands, 0, sizeof(speechState.displayedBands));
    speechState.positionMs = speechState.durationMs;
    speechState.phase = ok ? "complete" : "error";
    speechState.error = ok ? "" : "Playback exceeded its deadline";
    if (!drained) speechState.ready = false;
    portEXIT_CRITICAL(&speechMux);
  }
}

void startSpeech() {
  M5.Speaker.end();
  auto config = M5.Speaker.config();
  config.sample_rate = speechRate;
  config.dma_buf_len = 128;
  config.dma_buf_count = 4;
  config.task_priority = 3;
  M5.Speaker.config(config);
  M5.Speaker.setVolume(255);
  bool ready = M5.Speaker.begin(); // All amplifier I2C writes happen here.
  speechAvailable = xSemaphoreCreateBinary();
  ready = ready && speechAvailable &&
    xTaskCreate(playSpeech, "speech_pcm", 4096, nullptr, 1, nullptr) == pdPASS;
  speechState.ready = ready;
  speechState.phase = ready ? "idle" : "unavailable";
}

esp_err_t speechControl(httpd_req_t* req) {
  if (!authorized(req)) return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Forbidden");
  if (req->method == HTTP_POST) {
    if (req->content_len <= 0 || req->content_len > maxSpeechBytes || req->content_len % 2)
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected up to 20 seconds of mono 24kHz S16LE PCM");
    char type[48] = {};
    httpd_req_get_hdr_value_str(req, "Content-Type", type, sizeof(type));
    if (strcmp(type, "application/octet-stream"))
      return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected application/octet-stream");
    SpeechState state = getSpeechState();
    if (!state.ready || state.busy) {
      httpd_resp_set_status(req, state.ready ? "409 Conflict" : "503 Service Unavailable");
      return httpd_resp_send(req, state.ready ? "Speech already active; no queue" : "Speaker unavailable", HTTPD_RESP_USE_STRLEN);
    }
    int16_t* pcm = (int16_t*)heap_caps_malloc(req->content_len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!pcm) {
      httpd_resp_set_status(req, "503 Service Unavailable");
      return httpd_resp_send(req, "Speech memory unavailable", HTTPD_RESP_USE_STRLEN);
    }
    portENTER_CRITICAL(&speechMux);
    speechState.busy = true; speechState.phase = "uploading";
    portEXIT_CRITICAL(&speechMux);
    size_t received = 0;
    while (received < req->content_len) {
      int count = httpd_req_recv(req, (char*)pcm + received, min(size_t(4096), req->content_len - received));
      if (count <= 0) { free(pcm); speechError("Speech upload interrupted"); return ESP_FAIL; }
      received += count;
    }
    speechPcm = pcm; speechSampleCount = req->content_len / 2;
    portENTER_CRITICAL(&speechMux);
    speechState.clipId++;
    speechState.durationMs = speechSampleCount * 1000 / speechRate;
    speechState.positionMs = speechState.renderedFrames = speechState.silentFrames = speechState.voicedFrames = 0;
    speechState.mouth = speechState.displayedMouth = 0;
    memset(speechState.bands, 0, sizeof(speechState.bands));
    memset(speechState.displayedBands, 0, sizeof(speechState.displayedBands));
    speechState.phase = "preparing"; speechState.error = "";
    portEXIT_CRITICAL(&speechMux);
    xSemaphoreGive(speechAvailable);
    httpd_resp_set_status(req, "202 Accepted");
  }
  SpeechState state = getSpeechState();
  JsonDocument out;
  out["ready"] = state.ready; out["busy"] = state.busy; out["playing"] = state.active;
  out["phase"] = state.phase; out["error"] = state.error;
  out["clip_id"] = state.clipId; out["duration_ms"] = state.durationMs;
  out["position_ms"] = state.positionMs; out["mouth_open"] = state.mouth;
  out["displayed_mouth_open"] = state.displayedMouth;
  out["audio_level"] = state.mouth;
  out["displayed_audio_level"] = state.displayedMouth;
  out["audio_visual"] = "mouth_spectrum";
  out["volume"] = M5.Speaker.getVolume();
  out["volume_max"] = 255;
  JsonArray bands = out["audio_bands"].to<JsonArray>();
  JsonArray displayed = out["displayed_audio_bands"].to<JsonArray>();
  for (size_t b = 0; b < speechBands; b++) { bands.add(state.bands[b]); displayed.add(state.displayedBands[b]); }
  out["band_analysis"] = "broad_filter_bank_200_500_1200_3000_hz";
  out["mouth_frames"] = state.renderedFrames; out["silent_mouth_frames"] = state.silentFrames;
  out["voiced_mouth_frames"] = state.voicedFrames;
  out["clock"] = "scheduled_pcm_with_dma_offset";
  out["sample_rate"] = speechRate; out["firmware"] = "0.6.7";
  String encoded; serializeJson(out, encoded);
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  return httpd_resp_send(req, encoded.c_str(), encoded.length());
}

void registerSpeech(httpd_handle_t controlServer) {
  httpd_uri_t endpoint = {};
  endpoint.uri = "/speech"; endpoint.handler = speechControl;
  endpoint.method = HTTP_GET; httpd_register_uri_handler(controlServer, &endpoint);
  endpoint.method = HTTP_POST; httpd_register_uri_handler(controlServer, &endpoint);
}
