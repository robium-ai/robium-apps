import { RobotScene } from "/sim/js/scene.js";
import { FaceRenderer } from "/sim/js/face_renderer.js";

const statusEl = document.querySelector("#status");
const brainBadge = document.querySelector("#brain-badge");
const transcriptEl = document.querySelector("#transcript");
const replyEl = document.querySelector("#reply");
const form = document.querySelector("#command-form");
const input = document.querySelector("#command-input");
const micButton = document.querySelector("#mic-button");
const micLabel = document.querySelector("#mic-label");
const cameraCard = document.querySelector("#camera-card");
const trackingButton = document.querySelector("#tracking-button");
const trackingState = document.querySelector("#tracking-state");
const video = document.querySelector("#camera");
const overlay = document.querySelector("#camera-overlay");
const robotViewport = document.querySelector("#robot-viewport");
const simStatus = document.querySelector("#sim-status");
const simSpeech = document.querySelector("#sim-speech");

let recording = null;
let tracking = false;
let tracker = null;
let cameraStream = null;
let lastTrackPost = 0;
let lastFaceSeen = 0;
let lostCentered = false;
let smoothX = 0.5;
let smoothY = 0.5;
let robotScene = null;
let robotFace = null;
let robotModel = null;
let simulatorSocket = null;

function setStatus(message) { statusEl.textContent = message; }

async function startRobotViewer() {
  robotModel = await jsonFetch("/api/model");
  robotScene = new RobotScene(robotViewport);
  await robotScene.build(robotModel);
  if (robotScene.gazeArrow) robotScene.gazeArrow.visible = false;
  robotFace = new FaceRenderer();
  robotScene.attachFaceCanvas(robotFace.canvas);
  connectRobotTelemetry();
}

function connectRobotTelemetry() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  simulatorSocket = new WebSocket(`${protocol}//${location.host}/ws`);
  simulatorSocket.addEventListener("open", () => { simStatus.textContent = "MuJoCo live"; });
  simulatorSocket.addEventListener("message", (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (message.type !== "telemetry" || !robotScene) return;
    robotScene.setAngles(message.pan, message.tilt);
    const limits = robotModel.limits;
    robotFace.update({
      expression: message.expression,
      mouthOpen: message.mouth_open,
      pan: message.pan,
      tilt: message.tilt,
      panRange: Math.max(Math.abs(limits.pan_min), Math.abs(limits.pan_max)),
      tiltRange: { min: limits.tilt_min, max: limits.tilt_max },
      gazeMode: "follow",
    });
    simSpeech.textContent = message.speech_text || "";
    simSpeech.classList.toggle("is-hidden", !message.speech_text);
  });
  simulatorSocket.addEventListener("close", () => {
    simStatus.textContent = "MuJoCo reconnecting…";
    window.setTimeout(connectRobotTelemetry, 800);
  });
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* response is not JSON */ }
    throw new Error(detail);
  }
  return response.json();
}

async function playSpeech(text) {
  if (!text) return;
  setStatus("Kokoro is speaking locally…");
  const response = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error(`TTS failed (${response.status})`);
  const audio = new Audio(URL.createObjectURL(await response.blob()));
  await audio.play();
  audio.addEventListener("ended", () => setStatus(tracking ? "Tracking your face" : "Ready"), { once: true });
}

async function sendCommand(text) {
  text = text.trim();
  if (!text) return;
  transcriptEl.textContent = text;
  setStatus("Thinking…");
  const result = await jsonFetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  replyEl.textContent = result.speech || "Done.";
  if (result.tracking === "start") await startTracking();
  if (result.tracking === "stop") await stopTracking();
  await playSpeech(result.speech);
  if (!result.speech) setStatus(tracking ? "Tracking your face" : "Ready");
}

async function runCommand(text) {
  try { await sendCommand(text); }
  catch (error) { setStatus(`Error: ${error.message}`); replyEl.textContent = "Something went wrong."; }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value;
  input.value = "";
  runCommand(text);
});

document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("click", () => runCommand(button.dataset.command));
});

async function beginRecording() {
  if (recording) return;
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true }, video: false });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const mute = context.createGain();
  mute.gain.value = 0;
  const chunks = [];
  processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  source.connect(processor);
  processor.connect(mute);
  mute.connect(context.destination);
  recording = { stream, context, source, processor, mute, chunks, sampleRate: context.sampleRate };
  micButton.classList.add("is-recording");
  micLabel.textContent = "Listening… release to send";
  setStatus("Recording locally…");
}

async function endRecording() {
  if (!recording) return;
  const current = recording;
  recording = null;
  micButton.classList.remove("is-recording");
  micButton.disabled = true;
  micLabel.textContent = "Transcribing…";
  current.processor.disconnect();
  current.source.disconnect();
  current.mute.disconnect();
  current.stream.getTracks().forEach((track) => track.stop());
  await current.context.close();
  const count = current.chunks.reduce((total, chunk) => total + chunk.length, 0);
  const audio = new Float32Array(count);
  let offset = 0;
  for (const chunk of current.chunks) { audio.set(chunk, offset); offset += chunk.length; }
  try {
    const result = await jsonFetch(`/api/transcribe?sample_rate=${current.sampleRate}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: audio.buffer,
    });
    await sendCommand(result.text || "");
  } catch (error) {
    setStatus(`Voice error: ${error.message}`);
  } finally {
    micButton.disabled = false;
    micLabel.textContent = "Hold to talk";
  }
}

micButton.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  micButton.setPointerCapture(event.pointerId);
  beginRecording().catch((error) => setStatus(`Microphone unavailable: ${error.message}`));
});
micButton.addEventListener("pointerup", (event) => { event.preventDefault(); endRecording(); });
micButton.addEventListener("pointercancel", () => endRecording());

async function loadTracker() {
  if (tracker) return tracker;
  setStatus("Loading the browser-local face tracker…");
  const vision = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/+esm");
  const files = await vision.FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm"
  );
  tracker = await vision.FaceLandmarker.createFromOptions(files, {
    baseOptions: {
      modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numFaces: 3,
  });
  return tracker;
}

function largestFace(faces) {
  let selected = null;
  let largest = 0;
  for (const landmarks of faces) {
    let minX = 1, maxX = 0, minY = 1, maxY = 0;
    for (const point of landmarks) {
      minX = Math.min(minX, point.x); maxX = Math.max(maxX, point.x);
      minY = Math.min(minY, point.y); maxY = Math.max(maxY, point.y);
    }
    const area = (maxX - minX) * (maxY - minY);
    if (area > largest) { largest = area; selected = { minX, maxX, minY, maxY }; }
  }
  return selected;
}

async function postFace(x, y) {
  await fetch("/api/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ x, y, confidence: 1 }),
  });
}

function trackingLoop(now) {
  if (!tracking) return;
  const canvas = overlay;
  const context = canvas.getContext("2d");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 360;
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (video.readyState >= 2) {
    const face = largestFace(tracker.detectForVideo(video, now).faceLandmarks || []);
    if (face) {
      const x = (face.minX + face.maxX) / 2;
      const y = (face.minY + face.maxY) / 2;
      smoothX = 0.75 * smoothX + 0.25 * x;
      smoothY = 0.75 * smoothY + 0.25 * y;
      lastFaceSeen = now;
      lostCentered = false;
      context.strokeStyle = "#efb35f";
      context.lineWidth = 4;
      context.strokeRect(face.minX * canvas.width, face.minY * canvas.height,
        (face.maxX - face.minX) * canvas.width, (face.maxY - face.minY) * canvas.height);
      if (now - lastTrackPost > 100) { lastTrackPost = now; postFace(smoothX, smoothY); }
      trackingState.textContent = "Following face";
    } else if (now - lastFaceSeen > 900 && !lostCentered) {
      lostCentered = true;
      postFace(0.5, 0.5);
      trackingState.textContent = "Face lost · holding center";
    }
  }
  requestAnimationFrame(trackingLoop);
}

async function startTracking() {
  if (tracking) return;
  await loadTracker();
  cameraStream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 360 }, facingMode: "user" }, audio: false,
  });
  video.srcObject = cameraStream;
  await video.play();
  tracking = true;
  lastFaceSeen = performance.now();
  cameraCard.classList.add("is-active");
  trackingButton.textContent = "Stop tracking";
  trackingState.textContent = "Looking for a face";
  setStatus("Tracking locally in this browser tab");
  requestAnimationFrame(trackingLoop);
}

async function stopTracking() {
  tracking = false;
  if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  video.srcObject = null;
  cameraCard.classList.remove("is-active");
  trackingButton.textContent = "Enable camera";
  trackingState.textContent = "Off";
  await fetch("/api/track/stop", { method: "POST" });
  setStatus("Ready");
}

trackingButton.addEventListener("click", () => {
  (tracking ? stopTracking() : startTracking()).catch((error) => setStatus(`Camera unavailable: ${error.message}`));
});

jsonFetch("/api/status")
  .then((state) => {
    brainBadge.textContent = `${state.brain} brain`;
    setStatus(state.speech.stt === "ready" && state.speech.tts === "ready" ? "Ready" : "Run ./app build to install speech models");
  })
  .catch((error) => setStatus(`Backend unavailable: ${error.message}`));

startRobotViewer().catch((error) => { simStatus.textContent = `MuJoCo error: ${error.message}`; });
