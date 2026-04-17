from __future__ import annotations

import importlib.metadata
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .api import AppBridgeApi

DEFAULT_BRIDGE_HTML = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>YT Downloader bridge shell</title>
    <style>
      :root {
        color-scheme: light;
        font-family: "Segoe UI", sans-serif;
      }

      body {
        margin: 0;
        padding: 24px;
        background: linear-gradient(180deg, #f4f1e8 0%, #e5ecf5 100%);
        color: #1f2937;
      }

      h1 {
        margin: 0 0 8px;
        font-size: 28px;
      }

      p {
        max-width: 780px;
        line-height: 1.5;
      }

      .panel {
        margin-top: 18px;
        padding: 16px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.84);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
      }

      pre {
        overflow: auto;
        padding: 12px;
        border-radius: 10px;
        background: #101826;
        color: #dbe4f0;
      }
    </style>
  </head>
  <body>
    <h1>YT Downloader bridge shell</h1>
    <p>
      React frontend assets were not found under <code>frontend/dist</code>. Build them with
      <code>npm install</code> and <code>npm run build</code>, or point the shell at a running
      Vite dev server with <code>--bridge-start-url http://localhost:5173</code>.
    </p>
    <div class="panel">
      <strong>Runtime</strong>
      <pre id="runtime">Loading runtime info...</pre>
    </div>
    <div class="panel">
      <strong>App state</strong>
      <pre id="state">Loading app state...</pre>
    </div>
    <script>
      const runtimeNode = document.getElementById("runtime");
      const stateNode = document.getElementById("state");
      let lastCursor = 0;

      function formatPayload(payload) {
        return JSON.stringify(payload, null, 2);
      }

      async function refreshBridgeState() {
        if (!window.pywebview?.api) {
          stateNode.textContent = "pywebview bridge API is not ready yet.";
          return;
        }

        const runtime = await window.pywebview.api.get_runtime_info();
        runtimeNode.textContent = formatPayload(runtime);

        const appState = await window.pywebview.api.get_app_state({ since_event_id: lastCursor });
        lastCursor = appState.meta?.event_cursor ?? lastCursor;
        stateNode.textContent = formatPayload(appState);
      }

      window.addEventListener("pywebviewready", () => {
        refreshBridgeState();
        window.setInterval(refreshBridgeState, 1000);
      });
    </script>
  </body>
</html>
"""


class BridgeHostError(RuntimeError):
    exit_code = 2


class BridgeHostUnavailableError(BridgeHostError):
    pass


class BridgeHostStartupError(BridgeHostError):
    pass


@dataclass(slots=True, frozen=True)
class BridgeHostEnvironment:
    pywebview_version: str
    module_path: str


@dataclass(slots=True, frozen=True)
class BridgeLaunchTarget:
    kind: str
    value: str


class PywebviewHost:
    title = "YT Downloader bridge shell"

    def __init__(self, bridge_api: AppBridgeApi) -> None:
        self.bridge_api = bridge_api

    def probe_environment(self) -> BridgeHostEnvironment:
        webview = self._load_webview()
        return BridgeHostEnvironment(
            pywebview_version=importlib.metadata.version("pywebview"),
            module_path=getattr(webview, "__file__", "") or "",
        )

    def resolve_launch_target(self, *, start_url: str | None = None) -> BridgeLaunchTarget:
        normalized_start_url = (start_url or "").strip()
        if normalized_start_url:
            return BridgeLaunchTarget(kind="url", value=normalized_start_url)

        build_index = self._built_index_path()
        if build_index.exists():
            return BridgeLaunchTarget(kind="file", value=build_index.as_uri())

        return BridgeLaunchTarget(kind="inline_html", value="")

    def run(
        self,
        *,
        start_url: str | None = None,
        debug: bool = False,
        auto_close_after: float | None = None,
    ) -> BridgeHostEnvironment:
        environment = self.probe_environment()
        webview = self._load_webview()
        launch_target = self.resolve_launch_target(start_url=start_url)
        window_kwargs = {
            "js_api": self.bridge_api,
            "width": 1180,
            "height": 820,
        }
        if auto_close_after is not None:
            window_kwargs.update(
                {
                    "width": 720,
                    "height": 540,
                }
            )

        try:
            if launch_target.kind in {"url", "file"}:
                window = webview.create_window(
                    self.title,
                    url=launch_target.value,
                    **window_kwargs,
                )
            else:
                window = webview.create_window(self.title, html=DEFAULT_BRIDGE_HTML, **window_kwargs)

            if auto_close_after is not None:
                webview.start(
                    self._destroy_after_delay,
                    args=(window, auto_close_after),
                    debug=debug,
                )
            else:
                webview.start(debug=debug)
        except BridgeHostError:
            raise
        except Exception as error:  # pragma: no cover - real GUI backend failures are environment-specific
            raise BridgeHostStartupError(f"Failed to start pywebview host: {error}") from error
        return environment

    @staticmethod
    def _destroy_after_delay(window: object, delay_seconds: float) -> None:
        time.sleep(max(delay_seconds, 0.1))
        destroy = getattr(window, "destroy", None)
        if callable(destroy):
            destroy()

    @staticmethod
    def _load_webview() -> ModuleType:
        try:
            import webview
        except ImportError as error:
            raise BridgeHostUnavailableError(
                "pywebview is not available in the active Poetry environment. Run `poetry install`."
            ) from error
        return webview

    @staticmethod
    def _built_index_path() -> Path:
        return Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
