/* Presentation-only translations; detection values and thresholds stay intact. */
(() => {
  const english = {
    "DriveGuard · 驾驶员疲劳感知": "DriveGuard · Driver Fatigue Monitoring",
    "EE6008 本地驾驶员疲劳感知仪表盘": "EE6008 local driver fatigue monitoring dashboard",
    "界面语言": "Interface language",
    "本地处理 · 画面不上传": "Local processing · No video upload",
    "正在连接本地服务…": "Connecting to the local service…",
    "驾驶员监测画面": "Driver monitoring",
    "摄像头尚未启动": "Camera is off",
    "启动后先保持睁眼、闭嘴约 5 秒": "Keep your eyes open and mouth closed for about 5 seconds after starting",
    "本地输入": "Local input",
    "系统待机": "Ready to monitor",
    "点击开始监测，系统会先建立个人面部基准。": "Start monitoring to establish your personal facial baseline.",
    "疲劳指标": "Fatigue indicators",
    "人脸状态": "Face presence",
    "EAR 眼睛": "Eyes · EAR",
    "MAR 嘴巴": "Mouth · MAR",
    "持续闭眼": "Continuous eye closure",
    "近期哈欠": "Recent yawns",
    "手机状态": "Phone detection",
    "YOLO26n · 本地CPU": "YOLO26n · Local inference",
    "头部姿态": "Head pose",
    "俯仰": "Pitch",
    "左右": "Yaw",
    "侧倾": "Roll",
    "Head pose · 偏离前方持续 2 秒后提醒": "Head pose · Alert after 2 seconds looking away",
    "状态记录": "Event timeline",
    "等待开始监测": "Waiting to start",
    "所有计算将在本机完成": "All processing takes place on this computer",
    "输入来源": "Input source",
    "摄像头": "Camera",
    "本地视频": "Local video",
    "本地视频完整路径": "Full path to a local video",
    "粘贴这台电脑上的视频完整路径": "Paste the full path to a video on this computer",
    "文件只在本机读取，不会上传。片段开头应正常睁眼、闭嘴，供个人校准。": "Read locally with no upload. Start the clip with eyes open and mouth closed for calibration.",
    "开始监测": "Start monitoring",
    "开始分析": "Analyze video",
    "重新校准": "Recalibrate",
    "停止": "Stop",
    "待机": "Standby",
    "启动校准：正对镜头，正常睁眼、闭嘴。约 5 秒有效画面后开始监测；人脸丢失或明显转头时暂停计时。": "Startup calibration: face the camera with eyes open and mouth closed. Monitoring starts after about 5 seconds of valid observations; the timer pauses if your face is lost or turned away.",
    "当前检测画面中的手机，尚不能确认是否正在使用。": "Detects phones in view; phone use is not yet confirmed.",
    "正在启动": "Starting",
    "正在打开摄像头并加载人脸模型…": "Opening the camera and loading the face model…",
    "正在打开本地视频并加载人脸模型…": "Opening the video and loading the face model…",
    "正在停止": "Stopping",
    "正在释放输入资源…": "Releasing the input…",
    "正在停止并释放输入资源…": "Stopping and releasing the input…",
    "视频分析完成": "Video analysis complete",
    "可以选择其他视频或再次开始分析": "Choose another video or analyze it again",
    "正在个人校准": "Personal calibration",
    "正常睁眼、闭嘴并正对镜头": "Keep your eyes open, mouth closed, and face the camera",
    "请正常睁眼、闭嘴并正对镜头": "Keep your eyes open, mouth closed, and face the camera",
    "请让脸完整出现在画面中": "Keep your full face visible in the frame",
    "正在使用视频开头建立个人基准": "Establishing the personal baseline from the start of the video",
    "状态正常": "Normal",
    "当前没有检测到持续疲劳信号": "No sustained fatigue indicators detected",
    "需要注意": "Warning",
    "检测到需要注意的驾驶员状态": "Driver attention is required",
    "疲劳危险": "High fatigue risk",
    "检测到持续疲劳风险，请及时休息": "Sustained fatigue indicators detected. Please take a break.",
    "运行异常": "Runtime error",
    "请查看事件记录中的错误信息": "Check the event timeline for error details",
    "人脸长时间离开画面": "Face missing for an extended period",
    "闭眼时间过长": "Prolonged eye closure",
    "正在打哈欠": "Yawning",
    "频繁打哈欠": "Repeated yawning",
    "闭眼占比较高": "Elevated closed-eye ratio",
    "闭眼占比过高": "High closed-eye ratio",
    "状态恢复确认中": "Confirming recovery",
    "持续低头": "Sustained head-down posture",
    "持续偏离前方": "Sustained looking away",
    "持续检测到手机": "Sustained phone detection",
    "视频分析已结束": "Video analysis has ended",
    "本地视频尚未启动": "Video analysis has not started",
    "填写视频完整路径后，点击开始分析": "Enter a full video path, then select Analyze video",
    "正在建立片段中的个人基准": "Establishing the baseline from this clip",
    "请保持自然状态": "Keep your eyes open, mouth closed, and face the camera",
    "{prompt}，还需约 {seconds} 秒 · {samples} 帧": "{prompt} · {seconds} s remaining · {samples} samples",
    "已检测": "Detected",
    "未检测": "Not detected",
    "闭眼阈值 {value}": "Eye-closure threshold {value}",
    "张嘴阈值 {value}": "Mouth-opening threshold {value}",
    "{value} 秒": "{value} s",
    "{value} 次": "{value}",
    "已出现 {value} 秒": "Detected for {value} s",
    "手机检测已关闭": "Phone detection disabled",
    "等待校准完成": "Pending",
    "校准后开始手机检测": "Phone detection starts after calibration",
    "本地推理": "Local inference",
    "已偏离前方 {value} 秒": "Looking away for {value} s",
    "停止中": "Stopping",
    "启动中": "Starting",
    "校准中": "Calibrating",
    "分析中 · {frames} 帧": "Analyzing · {frames} frames",
    "实时": "Live",
    "已完成": "Completed",
    "本地服务未响应": "The local service is not responding",
    "操作失败，请检查输入": "The operation failed. Please check your input.",
    "请选择摄像头或本地视频": "Select a camera or a local video",
    "请输入本地视频的完整路径": "Enter the full path to a local video",
    "找不到本地视频文件，请检查路径": "Video file not found. Please check the path.",
    "使用视频路径时，请选择本地视频输入": "Select Local video when using a video path",
    "监测尚未启动": "Monitoring has not started",
    "摄像头画面已经结束": "The camera stream has ended",
    "监测已停止": "Monitoring stopped",
    "监测启动": "Monitoring started",
    "监测停止": "Monitoring stopped",
    "输入资源已安全释放": "Input resources released",
    "个人校准完成": "Personal calibration complete",
    "运行错误": "Runtime error",
    "当前状态稳定": "Current status is stable",
    "状态变为 {state}": "Status changed to {state}",
    "摄像头 {index}": "Camera {index}",
    "视频 · {name}": "Video · {name}",
    "视频分析完成，共处理 {frames} 帧": "Video analysis complete · {frames} frames processed",
    "；未完成个人校准，未生成疲劳判断": "; calibration was not completed, so no fatigue assessment was produced",
  };

  let language = "en";
  try {
    const requested = new URLSearchParams(window.location.search).get("lang");
    const saved = window.localStorage.getItem("driveguard-language");
    language = ["en", "zh"].includes(requested) ? requested
      : ["en", "zh"].includes(saved) ? saved : "en";
  } catch (_) { /* English is the default if storage is unavailable. */ }

  function t(key, values = {}) {
    const template = language === "en" ? (english[key] || key) : key;
    return template.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? `{${name}}`));
  }

  function serverText(value) {
    const text = String(value || "");
    if (language === "zh" || !text) return text;
    if (english[text]) return english[text];
    if (text.startsWith("摄像头 ")) return t("摄像头 {index}", { index: text.slice(4) });
    if (text.startsWith("视频 · ")) return t("视频 · {name}", { name: text.slice(5) });
    if (text.startsWith("状态变为 ")) return t("状态变为 {state}", { state: serverText(text.slice(5)) });
    const completed = text.match(/^视频分析完成，共处理 (\d+) 帧(.*)$/);
    if (completed) return t("视频分析完成，共处理 {frames} 帧", { frames: completed[1] })
      + serverText(completed[2]);
    if (text.includes("、")) return text.split("、").map(serverText).join(" · ");
    return text;
  }

  function applyStaticTranslations() {
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    document.title = t("DriveGuard · 驾驶员疲劳感知");
    document.querySelector('meta[name="description"]').content = t("EE6008 本地驾驶员疲劳感知仪表盘");
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-label]").forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nLabel));
    });
    document.querySelectorAll("[data-i18n-alt]").forEach((element) => {
      element.alt = t(element.dataset.i18nAlt);
    });
    document.querySelector("#language-select").value = language;
  }

  function setLanguage(value) {
    if (!["en", "zh"].includes(value)) return;
    language = value;
    try { window.localStorage.setItem("driveguard-language", language); } catch (_) {}
    // Keep explicit professor-demo links consistent with the selected language.
    const url = new URL(window.location.href);
    url.searchParams.set("lang", language);
    window.history.replaceState(null, "", url);
    applyStaticTranslations();
  }

  window.DriveGuardI18n = {
    t, serverText, applyStaticTranslations, setLanguage,
    locale: () => language === "en" ? "en-GB" : "zh-CN",
  };
})();
