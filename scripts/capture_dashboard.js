const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME_PATH =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9223;

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getDebuggerUrl() {
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === "page");
      if (page && page.webSocketDebuggerUrl) {
        return page.webSocketDebuggerUrl;
      }
    } catch (e) {
      // Chrome starting up
    }
    await sleep(200);
  }
  throw new Error("Could not connect to Chrome debugging endpoint");
}

async function capture() {
  console.log("Starting headless Chrome on port", PORT);
  const chrome = spawn(
    CHROME_PATH,
    [
      `--remote-debugging-port=${PORT}`,
      "--headless=new",
      "--disable-gpu",
      "--window-size=1600,1050",
      "http://localhost:8080/",
    ],
    { stdio: "ignore" },
  );

  try {
    const wsUrl = await getDebuggerUrl();
    console.log("Connected to Chrome CDP:", wsUrl);

    const ws = new WebSocket(wsUrl);
    let idCounter = 1;
    const pendingCallbacks = new Map();

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.id && pendingCallbacks.has(data.id)) {
        const cb = pendingCallbacks.get(data.id);
        pendingCallbacks.delete(data.id);
        cb(data.result || data.error);
      }
    };

    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });

    function send(method, params = {}) {
      return new Promise((resolve) => {
        const id = idCounter++;
        pendingCallbacks.set(id, resolve);
        ws.send(JSON.stringify({ id, method, params }));
      });
    }

    console.log("Enabling Page & Runtime...");
    await send("Page.enable");
    await send("Runtime.enable");

    // Wait a bit for initial page load
    await sleep(1500);

    console.log("Submitting login form to authenticate with backend API...");
    await send("Runtime.evaluate", {
      expression: `
                (async () => {
                    document.getElementById('loginEmail').value = 'admin@png261.dev';
                    document.getElementById('loginPassword').value = 'SuperNextcloud2026!SecureKey_mjOQ';
                    const form = document.getElementById('loginForm');
                    const event = new Event('submit', { cancelable: true, bubbles: true });
                    form.dispatchEvent(event);
                })()
            `,
      awaitPromise: true,
    });

    console.log("Waiting for tenants data and charts to render...");
    await sleep(3500);

    console.log("Capturing dashboard screenshot...");
    const screenshotRes = await send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
    });

    if (screenshotRes && screenshotRes.data) {
      const buf = Buffer.from(screenshotRes.data, "base64");
      const targetPaths = [
        path.join(
          __dirname,
          "../reports/2026-10-05/screenshots/control_panel_dashboard.png",
        ),
        "/Users/png/.gemini/antigravity/brain/a37cbf04-a713-44ee-854c-916ef58bb5c1/screenshots/control_panel_dashboard.png",
      ];
      for (const p of targetPaths) {
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, buf);
        console.log(`Saved screenshot to ${p} (${buf.length} bytes)`);
      }
    }

    console.log("Switching to Live CloudWatch Telemetry tab...");
    await send("Runtime.evaluate", {
      expression: `switchTab('cloudwatch');`,
      awaitPromise: true,
    });

    console.log("Waiting for CloudWatch telemetry widgets to load...");
    await sleep(4000);

    console.log("Capturing telemetry screenshot...");
    const telemetryRes = await send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
    });

    if (telemetryRes && telemetryRes.data) {
      const buf = Buffer.from(telemetryRes.data, "base64");
      const targetPaths = [
        path.join(
          __dirname,
          "../reports/2026-10-05/screenshots/control_panel_telemetry.png",
        ),
        "/Users/png/.gemini/antigravity/brain/a37cbf04-a713-44ee-854c-916ef58bb5c1/screenshots/control_panel_telemetry.png",
      ];
      for (const p of targetPaths) {
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, buf);
        console.log(`Saved screenshot to ${p} (${buf.length} bytes)`);
      }
    }

    ws.close();
  } finally {
    chrome.kill();
  }
}

capture().catch((err) => {
  console.error("Capture error:", err);
  process.exit(1);
});
