import { createReadStream, existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const distDir = path.join(repoRoot, "frontend", "dist");
const port = Number(process.env.UI_PROOF_PORT || process.argv[2] || 4174);

if (!existsSync(path.join(distDir, "index.html"))) {
  console.error("frontend/dist/index.html is missing. Run `npm run build` first.");
  process.exit(1);
}

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const thumbnailSvg = encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#0f5c73" />
      <stop offset="100%" stop-color="#0b485d" />
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#bg)" rx="36" />
  <rect x="74" y="72" width="1132" height="576" fill="rgba(255,255,255,0.1)" rx="28" />
  <circle cx="264" cy="224" r="86" fill="rgba(255,255,255,0.18)" />
  <rect x="418" y="166" width="528" height="64" fill="rgba(255,255,255,0.88)" rx="20" />
  <rect x="418" y="270" width="370" height="36" fill="rgba(255,255,255,0.42)" rx="18" />
  <rect x="418" y="330" width="452" height="36" fill="rgba(255,255,255,0.24)" rx="18" />
  <rect x="150" y="436" width="980" height="78" fill="rgba(255,255,255,0.14)" rx="22" />
  <text x="150" y="612" fill="rgba(255,255,255,0.86)" font-family="Segoe UI, Arial, sans-serif" font-size="54">Research-backed utility shell proof</text>
</svg>
`.trim());

const proofState = {
  status_message: "Ready to download Desk Setup Tour.",
  queue: [
    {
      id: "item-proof-001",
      source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      title: "Desk Setup Tour",
      mode: "video",
      quality: "1080p | mp4 | video-only | fmt 137",
      status: "queued",
      processing_step: "queued",
      status_detail: "Ready to start.",
      output_path: "",
      error_message: "",
      selected_format_id: "137",
      created_at: "2026-04-17T09:00:00Z",
      updated_at: "2026-04-17T09:03:00Z",
      probe: {
        source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title: "Desk Setup Tour",
        channel: "Utility Research Lab",
        thumbnail: `data:image/svg+xml;charset=UTF-8,${thumbnailSvg}`,
        duration: 524,
        video_formats: [
          {
            format_id: "137",
            quality_label: "1080p | mp4 | video-only | fmt 137",
            ext: "mp4",
            note: "video-only",
          },
          {
            format_id: "248",
            quality_label: "720p | webm | video-only | fmt 248",
            ext: "webm",
            note: "video-only",
          },
          {
            format_id: "22",
            quality_label: "720p | mp4 | muxed | fmt 22",
            ext: "mp4",
            note: "muxed",
          },
        ],
        audio_formats: [
          {
            format_id: "140",
            quality_label: "128 kbps | m4a | audio-only | fmt 140",
            ext: "m4a",
            note: "audio-only",
          },
          {
            format_id: "251",
            quality_label: "160 kbps | webm | audio-only | fmt 251",
            ext: "webm",
            note: "audio-only",
          },
        ],
      },
    },
    {
      id: "item-proof-002",
      source_url: "https://www.youtube.com/watch?v=5qap5aO4i9A",
      title: "Ambient Focus Mix",
      mode: "audio",
      quality: "160 kbps | webm | audio-only | fmt 251",
      status: "completed",
      processing_step: "completed",
      status_detail: "Created final file Ambient Focus Mix.m4a.",
      output_path: "C:\\Users\\user\\Downloads\\YT Queue\\Ambient Focus Mix-84aa19d2.m4a",
      error_message: "",
      selected_format_id: "251",
      created_at: "2026-04-17T08:32:00Z",
      updated_at: "2026-04-17T08:40:00Z",
      probe: {
        source_url: "https://www.youtube.com/watch?v=5qap5aO4i9A",
        title: "Ambient Focus Mix",
        channel: "Utility Research Lab",
        thumbnail: `data:image/svg+xml;charset=UTF-8,${thumbnailSvg}`,
        duration: 14400,
        video_formats: [],
        audio_formats: [
          {
            format_id: "251",
            quality_label: "160 kbps | webm | audio-only | fmt 251",
            ext: "webm",
            note: "audio-only",
          },
        ],
      },
    },
    {
      id: "item-proof-003",
      source_url: "https://www.youtube.com/watch?v=ysz5S6PUM-U",
      title: "Walking Tour Sample",
      mode: "video",
      quality: "720p | mp4 | muxed | fmt 22",
      status: "failed",
      processing_step: "failed",
      status_detail: "failed at postprocessing",
      output_path: "",
      error_message: "ffmpeg is required to produce final mp4 output.",
      selected_format_id: "22",
      created_at: "2026-04-17T08:10:00Z",
      updated_at: "2026-04-17T08:15:00Z",
      probe: {
        source_url: "https://www.youtube.com/watch?v=ysz5S6PUM-U",
        title: "Walking Tour Sample",
        channel: "City Walks",
        thumbnail: `data:image/svg+xml;charset=UTF-8,${thumbnailSvg}`,
        duration: 733,
        video_formats: [
          {
            format_id: "22",
            quality_label: "720p | mp4 | muxed | fmt 22",
            ext: "mp4",
            note: "muxed",
          },
        ],
        audio_formats: [
          {
            format_id: "140",
            quality_label: "128 kbps | m4a | audio-only | fmt 140",
            ext: "m4a",
            note: "audio-only",
          },
        ],
      },
    },
  ],
  selected_item_id: "item-proof-001",
  selected_item: null,
  selection: {
    selected_item_id: "item-proof-001",
    mode: "video",
    quality: "1080p | mp4 | video-only | fmt 137",
    selected_format_id: "137",
    quality_options: [
      "1080p | mp4 | video-only | fmt 137",
      "720p | webm | video-only | fmt 248",
      "720p | mp4 | muxed | fmt 22",
    ],
  },
  runtime: {
    project_root: repoRoot,
    runtime_dir: path.join(repoRoot, "runtime"),
    output_dir: "C:\\Users\\user\\Downloads\\YT Queue",
    temp_dir: path.join(repoRoot, "runtime", "temp"),
    state_file: path.join(repoRoot, "runtime", "queue_state.json"),
    queue_items_loaded: 3,
    ffmpeg: {
      name: "ffmpeg",
      path: "C:\\Tools\\ffmpeg\\ffmpeg.exe",
      source: "bundle",
      is_available: true,
    },
    ffprobe: {
      name: "ffprobe",
      path: "C:\\Tools\\ffmpeg\\ffprobe.exe",
      source: "bundle",
      is_available: true,
    },
  },
};

function buildMockBridgeScript() {
  return `
const proofSeed = ${JSON.stringify(proofState)};

const clone = (value) => JSON.parse(JSON.stringify(value));
let state = clone(proofSeed);
let eventCursor = 7;

function currentItem() {
  return state.queue.find((item) => item.id === state.selected_item_id) || null;
}

function optionsForMode(item, mode) {
  const probe = item?.probe;
  if (!probe) {
    return [];
  }
  return mode === "audio" ? probe.audio_formats || [] : probe.video_formats || [];
}

function syncSelection() {
  const item = currentItem();
  if (!item) {
    state.selected_item = null;
    state.selection = {
      selected_item_id: "",
      mode: "video",
      quality: "",
      selected_format_id: "",
      quality_options: [],
    };
    return;
  }

  const options = optionsForMode(item, item.mode);
  const selectedOption =
    options.find((option) => option.quality_label === item.quality) ||
    options.find((option) => option.format_id === item.selected_format_id) ||
    options[0] ||
    null;

  if (selectedOption) {
    item.quality = selectedOption.quality_label;
    item.selected_format_id = selectedOption.format_id;
  }

  state.selected_item_id = item.id;
  state.selected_item = clone(item);
  state.selection = {
    selected_item_id: item.id,
    mode: item.mode,
    quality: item.quality,
    selected_format_id: item.selected_format_id,
    quality_options: options.map((option) => option.quality_label),
  };
  state.runtime.queue_items_loaded = state.queue.length;
}

function nextResponse(data) {
  return {
    ok: true,
    data,
    error: null,
    meta: {
      api_version: "bridge.v1",
      event_cursor: eventCursor,
      download_active: false,
    },
  };
}

function readField(payload, fieldName) {
  if (typeof payload === "string") {
    return payload.trim();
  }
  if (payload && typeof payload === "object") {
    return String(payload[fieldName] || "").trim();
  }
  return "";
}

function readCursor(payload) {
  if (typeof payload === "number") {
    return payload;
  }
  if (typeof payload === "string" && payload.trim()) {
    return Number(payload) || 0;
  }
  if (payload && typeof payload === "object") {
    return Number(payload.since_event_id || 0) || 0;
  }
  return 0;
}

function snapshot() {
  syncSelection();
  return clone(state);
}

function touch(statusMessage) {
  eventCursor += 1;
  state.status_message = statusMessage;
}

function selectItem(itemId) {
  const item = state.queue.find((entry) => entry.id === itemId);
  if (!item) {
    return;
  }
  state.selected_item_id = item.id;
  touch("Selected " + (item.title || item.source_url) + ".");
}

function selectMode(mode) {
  const item = currentItem();
  if (!item || (mode !== "video" && mode !== "audio")) {
    return;
  }
  item.mode = mode;
  const options = optionsForMode(item, mode);
  if (options[0]) {
    item.quality = options[0].quality_label;
    item.selected_format_id = options[0].format_id;
  }
  touch("Download option updated for " + (item.title || item.source_url) + ".");
}

function selectQuality(quality) {
  const item = currentItem();
  if (!item) {
    return;
  }
  const option = optionsForMode(item, item.mode).find((entry) => entry.quality_label === quality);
  if (!option) {
    return;
  }
  item.quality = option.quality_label;
  item.selected_format_id = option.format_id;
  touch("Download option updated for " + (item.title || item.source_url) + ".");
}

syncSelection();

window.pywebview = {
  api: {
    get_app_state(payload) {
      const sinceEventId = readCursor(payload);
      const stateSnapshot = snapshot();
      if (sinceEventId >= eventCursor) {
        return Promise.resolve(
          nextResponse({
            state_changed: false,
            events: [],
          }),
        );
      }
      return Promise.resolve(
        nextResponse({
          state_changed: true,
          events: [
            {
              event_id: eventCursor,
              event_type: "proof_state",
              emitted_at_unix_ms: Date.now(),
              state: stateSnapshot,
            },
          ],
          state: stateSnapshot,
        }),
      );
    },
    add_url(payload) {
      const url = readField(payload, "url");
      touch(url ? "Proof harness keeps a fixed queue. The entered link was not added." : state.status_message);
      return Promise.resolve(nextResponse({ state: snapshot() }));
    },
    select_item(payload) {
      selectItem(readField(payload, "item_id"));
      return Promise.resolve(nextResponse({ state: snapshot() }));
    },
    select_mode(payload) {
      selectMode(readField(payload, "mode"));
      return Promise.resolve(nextResponse({ state: snapshot() }));
    },
    select_quality(payload) {
      selectQuality(readField(payload, "quality"));
      return Promise.resolve(nextResponse({ state: snapshot() }));
    },
    pick_output_dir() {
      state.runtime.output_dir = "C:\\\\Users\\\\user\\\\Downloads\\\\YT Queue";
      touch("Downloads will be saved to " + state.runtime.output_dir + ".");
      return Promise.resolve(nextResponse({ state: snapshot() }));
    },
    start_download(payload) {
      const itemId = readField(payload, "item_id");
      if (itemId) {
        selectItem(itemId);
      }
      const item = currentItem();
      if (item) {
        item.status = "running";
        item.processing_step = "downloading";
        item.status_detail = "Proof harness download started.";
        touch("Starting download for " + (item.title || item.source_url) + ".");
      }
      return Promise.resolve(
        nextResponse({
          accepted: Boolean(item),
          item_id: item ? item.id : "",
          state: snapshot(),
        }),
      );
    },
    get_runtime_info() {
      const stateSnapshot = snapshot();
      return Promise.resolve(
        nextResponse({
          runtime: stateSnapshot.runtime,
          bridge: {
            api_version: "bridge.v1",
            download_active: false,
            active_download_item_id: "",
            update_model: {
              kind: "polling",
              state_method: "get_app_state",
              cursor_arg: "since_event_id",
              event_shape: "full_state_snapshot",
              max_retained_events: 64,
            },
            command_model: {
              start_download_async: true,
              mutations_blocked_while_downloading: true,
            },
            shells: {
              tkinter_fallback: false,
              pywebview_bootstrap: false,
            },
          },
        }),
      );
    },
    inspect_output() {
      return Promise.resolve(
        nextResponse({
          output_path: "",
          inspection: {
            format_name: "proof-shell",
            stream_types: ["video"],
          },
        }),
      );
    },
  },
};

window.dispatchEvent(new Event("pywebviewready"));
`;
}

async function buildIndexHtml() {
  const indexHtml = await readFile(path.join(distDir, "index.html"), "utf8");
  const mockTag = '<script src="/__proof_mock__.js"></script>';
  return indexHtml.replace("<head>", `<head>\n    ${mockTag}`);
}

function contentTypeFor(filePath) {
  return mimeTypes[path.extname(filePath).toLowerCase()] || "application/octet-stream";
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://127.0.0.1:${port}`);
  const pathname = url.pathname === "/" ? "/index.html" : url.pathname;

  if (pathname === "/__proof_mock__.js") {
    response.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8" });
    response.end(buildMockBridgeScript());
    return;
  }

  if (pathname === "/index.html") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(await buildIndexHtml());
    return;
  }

  const relativePath = pathname.replace(/^\/+/, "");
  const filePath = path.join(distDir, relativePath);
  if (!filePath.startsWith(distDir) || !existsSync(filePath)) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  response.writeHead(200, { "Content-Type": contentTypeFor(filePath) });
  createReadStream(filePath).pipe(response);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`ui-proof-server=http://127.0.0.1:${port}`);
});

function shutdown() {
  server.close(() => {
    process.exit(0);
  });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
