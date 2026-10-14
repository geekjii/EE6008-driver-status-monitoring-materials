const { t, serverText, applyStaticTranslations, setLanguage, locale } = window.DriveGuardI18n;

const ui = {
  language: document.querySelector("#language-select"),
  clock: document.querySelector("#local-clock"),
  connection: document.querySelector("#connection-badge"),
  live: document.querySelector("#live-badge"),
  feed: document.querySelector("#camera-feed"),
  placeholder: document.querySelector("#camera-placeholder"),
  placeholderTitle: document.querySelector("#placeholder-title"),
  placeholderDetail: document.querySelector("#placeholder-detail"),
  source: document.querySelector("#source-select"),
  sourceCaption: document.querySelector("#source-caption"),
  videoField: document.querySelector("#video-path-field"),
  videoPath: document.querySelector("#video-path"),
  fps: document.querySelector("#fps-value"),
  risk: document.querySelector("#risk-card"),
  stateTitle: document.querySelector("#state-title"),
  stateMessage: document.querySelector("#state-message"),
  face: document.querySelector("#face-value"),
  ear: document.querySelector("#ear-value"),
  earCaption: document.querySelector("#ear-caption"),
  mar: document.querySelector("#mar-value"),
  marCaption: document.querySelector("#mar-caption"),
  perclos: document.querySelector("#perclos-value"),
  perclosBar: document.querySelector("#perclos-bar"),
  closed: document.querySelector("#closed-value"),
  yawns: document.querySelector("#yawn-value"),
  phoneCard: document.querySelector("#phone-card"),
  phone: document.querySelector("#phone-value"),
  phoneCaption: document.querySelector("#phone-caption"),
  pitch: document.querySelector("#pitch-value"),
  yaw: document.querySelector("#yaw-value"),
  roll: document.querySelector("#roll-value"),
  poseCaption: document.querySelector("#pose-caption"),
  events: document.querySelector("#event-list"),
  start: document.querySelector("#start-button"),
  calibrate: document.querySelector("#calibrate-button"),
  stop: document.querySelector("#stop-button"),
};

const stateCopy = {
  IDLE: ["系统待机", "点击开始监测，系统会先建立个人面部基准。", "idle"],
  STARTING: ["正在启动", "正在打开摄像头并加载人脸模型…", "calibrating"],
  STOPPING: ["正在停止", "正在释放输入资源…", "idle"],
  COMPLETED: ["视频分析完成", "可以选择其他视频或再次开始分析", "normal"],
  CALIBRATING: ["正在个人校准", "正常睁眼、闭嘴并正对镜头", "calibrating"],
  NORMAL: ["状态正常", "当前没有检测到持续疲劳信号", "normal"],
  WARNING: ["需要注意", "检测到需要注意的驾驶员状态", "warning"],
  DANGER: ["疲劳危险", "检测到持续疲劳风险，请及时休息", "danger"],
  ERROR: ["运行异常", "请查看事件记录中的错误信息", "danger"],
};

const reasonLabels = {
  face_missing: "人脸长时间离开画面",
  eyes_closed: "持续闭眼",
  eyes_closed_too_long: "闭眼时间过长",
  yawning: "正在打哈欠",
  repeated_yawning: "频繁打哈欠",
  high_perclos: "闭眼占比较高",
  very_high_perclos: "闭眼占比过高",
  recovering: "状态恢复确认中",
  head_down: "持续低头",
  looking_away: "持续偏离前方",
  phone_detected: "持续检测到手机",
};

let requestPending = false;
let commandPending = false;
let latestStatus = null;
let connected = true;

function updateSourceControls() {
  const running = Boolean(latestStatus?.running);
  const video = ui.source.value === "video";
  ui.videoField.hidden = !video;
  ui.videoPath.required = video;
  ui.source.disabled = running || commandPending;
  ui.videoPath.disabled = running || commandPending;
  ui.start.disabled = running || commandPending || (video && !ui.videoPath.value.trim());
  ui.calibrate.disabled = !running || commandPending || latestStatus?.phase === "stopping";
  ui.stop.disabled = !running || commandPending || latestStatus?.phase === "stopping";
  if (!running) {
    ui.placeholderTitle.textContent = latestStatus?.phase === "completed"
      ? t("视频分析已结束")
      : video ? t("本地视频尚未启动") : t("摄像头尚未启动");
    ui.placeholderDetail.textContent = video
      ? t("填写视频完整路径后，点击开始分析")
      : t("启动后先保持睁眼、闭嘴约 5 秒");
  }
  ui.start.textContent = video ? t("开始分析") : t("开始监测");
}

function updateClock() {
  ui.clock.textContent = new Date().toLocaleTimeString(locale(), { hour12: false });
}

function formatMetric(value, digits = 3) {
  return value === null || value === undefined ? "--" : Number(value).toFixed(digits);
}

function formatAngle(value, running) {
  return running && value !== null && value !== undefined
    ? `${Number(value).toFixed(1)}°`
    : "--";
}

function setConnection(value) {
  connected = value;
  ui.connection.style.opacity = connected ? "1" : "0.55";
  ui.connection.querySelector("b").textContent = connected
    ? t("本地处理 · 画面不上传")
    : t("正在连接本地服务…");
}

function ensureVideoStream(running) {
  if (running && !ui.feed.getAttribute("src")) {
    ui.feed.src = `/api/video?session=${Date.now()}`;
  }
  if (!running && ui.feed.getAttribute("src")) {
    ui.feed.removeAttribute("src");
    ui.feed.classList.remove("is-visible");
    ui.placeholder.hidden = false;
  }
}

ui.feed.addEventListener("load", () => {
  if (!latestStatus?.running || !ui.feed.getAttribute("src")) return;
  ui.feed.classList.add("is-visible");
  ui.placeholder.hidden = true;
});

function renderEvents(events) {
  ui.events.replaceChildren();
  const rows = events.length
    ? events.slice(0, 6)
    : [{ title: t("等待开始监测"), detail: t("所有计算将在本机完成"), level: "info", timestamp: Date.now() / 1000 }];
  rows.forEach((event) => {
    const row = document.createElement("li");
    row.dataset.level = event.level || "info";
    const dot = document.createElement("span");
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    const detail = document.createElement("small");
    const eventTime = new Date(event.timestamp * 1000).toLocaleTimeString(locale(), {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    title.textContent = `${eventTime} · ${serverText(event.title)}`;
    detail.textContent = serverText(event.detail);
    copy.append(title, detail);
    row.append(dot, copy);
    ui.events.append(row);
  });
}

function render(data) {
  if (latestStatus && Number(data.updated_at) < Number(latestStatus.updated_at)) return;
  latestStatus = data;
  if (data.running) {
    ui.source.value = data.source;
    if (data.source === "video") ui.videoPath.value = data.video_path || "";
  }
  const [title, defaultMessage, visualState] = stateCopy[data.state] || stateCopy.IDLE;
  const reasons = (data.reasons || []).map((reason) => t(reasonLabels[reason] || reason));
  ui.risk.dataset.state = visualState;
  ui.stateTitle.textContent = t(title);
  if (data.state === "CALIBRATING" && data.face_detected) {
    const prompt = t(data.source === "video" ? "正在建立片段中的个人基准" : "请保持自然状态");
    ui.stateMessage.textContent = t("{prompt}，还需约 {seconds} 秒 · {samples} 帧", {
      prompt, seconds: Number(data.calibration_remaining_seconds).toFixed(1),
      samples: data.calibration_sample_count,
    });
  } else {
    ui.stateMessage.textContent = reasons.join(locale() === "zh-CN" ? "、" : " · ")
      || serverText(data.message) || t(defaultMessage);
  }

  ui.face.textContent = data.face_detected ? t("已检测") : data.running ? t("未检测") : "--";
  ui.ear.textContent = formatMetric(data.ear);
  ui.mar.textContent = formatMetric(data.mar);
  ui.earCaption.textContent = data.ear_threshold
    ? t("闭眼阈值 {value}", { value: Number(data.ear_threshold).toFixed(3) })
    : "Eye aspect ratio";
  ui.marCaption.textContent = data.mar_threshold
    ? t("张嘴阈值 {value}", { value: Number(data.mar_threshold).toFixed(3) })
    : "Mouth aspect ratio";
  ui.perclos.textContent = data.running ? `${(Number(data.perclos) * 100).toFixed(1)}%` : "--";
  ui.closed.textContent = data.running ? t("{value} 秒", { value: Number(data.eye_closed_seconds).toFixed(1) }) : "--";
  ui.yawns.textContent = data.running ? t("{value} 次", { value: data.recent_yawn_count }) : "--";
  ui.phone.textContent = !data.running
    ? "--"
    : data.phone_enabled === false ? t("手机检测已关闭")
      : data.phase === "starting" || data.phase === "calibrating" ? t("等待校准完成")
        : data.phone_detected
          ? `${(Number(data.phone_confidence) * 100).toFixed(0)}%`
          : t("未检测");
  ui.phoneCard.classList.toggle("is-detected", Boolean(data.phone_detected));
  ui.phoneCaption.textContent = data.phone_enabled === false ? t("手机检测已关闭")
    : data.running && (data.phase === "starting" || data.phase === "calibrating")
      ? t("校准后开始手机检测")
      : data.running && data.phone_detected
        ? t("已出现 {value} 秒", { value: Number(data.phone_seen_seconds).toFixed(1) })
        : data.running && data.phone_inference_ms
          ? `YOLO26n · ${Number(data.phone_inference_ms).toFixed(0)} ms`
          : `YOLO26n · ${data.phone_device ? data.phone_device.toUpperCase() : t("本地推理")}`;
  ui.pitch.textContent = formatAngle(data.head_pitch, data.running);
  ui.yaw.textContent = formatAngle(data.head_yaw, data.running);
  ui.roll.textContent = formatAngle(data.head_roll, data.running);
  ui.poseCaption.textContent = data.running && Number(data.head_away_seconds) > 0
    ? t("已偏离前方 {value} 秒", { value: Number(data.head_away_seconds).toFixed(1) })
    : t("Head pose · 偏离前方持续 2 秒后提醒");
  ui.fps.textContent = `${Number(data.fps).toFixed(1)} FPS`;
  ui.sourceCaption.textContent = serverText(data.source_label) || t("本地输入");

  const perclosPercent = Math.min(100, Math.max(0, Number(data.perclos) * 100));
  ui.perclosBar.style.width = `${perclosPercent}%`;
  ui.perclosBar.style.backgroundColor =
    perclosPercent >= 35 ? "var(--danger)" : perclosPercent >= 20 ? "var(--warning)" : "var(--lime)";

  ui.live.className = `live-badge ${data.running ? "is-live" : "is-idle"}`;
  ui.live.querySelector("span").textContent = data.running
    ? data.phase === "stopping" ? t("停止中")
      : data.phase === "starting" ? t("启动中")
        : data.phase === "calibrating" ? t("校准中")
          : data.source === "video" ? t("分析中 · {frames} 帧", { frames: data.frames_processed }) : t("实时")
    : data.phase === "completed" ? t("已完成") : t("待机");
  ui.live.querySelector("i").style.background = data.running ? "var(--lime)" : "#5f6874";
  updateSourceControls();
  ensureVideoStream(data.running && data.phase !== "stopping");
  renderEvents(data.events || []);
}

async function fetchStatus() {
  if (requestPending) return;
  requestPending = true;
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(t("本地服务未响应"));
    render(await response.json());
    setConnection(true);
  } catch (_error) {
    setConnection(false);
  } finally {
    requestPending = false;
  }
}

async function command(path, payload) {
  if (commandPending) return;
  commandPending = true;
  updateSourceControls();
  try {
    const response = await fetch(path, {
      method: "POST",
      ...(payload ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) } : {}),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof body.detail === "string" ? serverText(body.detail) : t("操作失败，请检查输入"));
    }
    if (body.status) render(body.status);
    setConnection(true);
  } finally {
    commandPending = false;
    updateSourceControls();
    await fetchStatus();
  }
}

ui.start.addEventListener("click", async () => {
  const source = ui.source.value;
  const videoPath = ui.videoPath.value.trim();
  if (source === "video" && !videoPath) return;
  try {
    await command("/api/start", { source, video_path: source === "video" ? videoPath : null });
  } catch (error) { window.alert(error.message); }
});

ui.source.addEventListener("change", updateSourceControls);
ui.videoPath.addEventListener("input", updateSourceControls);

ui.calibrate.addEventListener("click", async () => {
  try { await command("/api/recalibrate"); } catch (error) { window.alert(error.message); }
});

ui.stop.addEventListener("click", async () => {
  try { await command("/api/stop"); } catch (error) { window.alert(error.message); }
});

window.addEventListener("beforeunload", () => {
  if (!latestStatus?.running) return;
  navigator.sendBeacon("/api/stop", new Blob([], { type: "application/octet-stream" }));
});

ui.language.addEventListener("change", () => {
  setLanguage(ui.language.value);
  if (latestStatus) render(latestStatus);
  else { updateSourceControls(); renderEvents([]); }
  setConnection(connected);
  updateClock();
});

applyStaticTranslations();
updateClock();
updateSourceControls();
window.setInterval(updateClock, 1000);
window.setInterval(fetchStatus, 250);
fetchStatus();
