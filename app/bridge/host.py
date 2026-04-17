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
        font-family: "Bahnschrift", "Segoe UI", sans-serif;
      }

      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 28px;
        background:
          radial-gradient(circle at top left, rgba(225, 163, 76, 0.18), transparent 30%),
          linear-gradient(180deg, #f7f3ea 0%, #eef3f7 100%);
        color: #1d2731;
      }

      .shell {
        width: min(720px, 100%);
        padding: 28px;
        border-radius: 24px;
        border: 1px solid rgba(84, 99, 115, 0.14);
        background: rgba(255, 255, 255, 0.94);
        box-shadow: 0 16px 40px rgba(35, 50, 66, 0.08);
      }

      h1 {
        margin: 0 0 10px;
        font-size: 30px;
        letter-spacing: -0.03em;
      }

      p {
        margin: 0;
        line-height: 1.6;
        color: #596673;
      }

      code {
        padding: 1px 6px;
        border-radius: 999px;
        background: rgba(11, 102, 131, 0.1);
        color: #0d4763;
      }

      details {
        margin-top: 18px;
        border-top: 1px solid rgba(84, 99, 115, 0.14);
        padding-top: 18px;
      }

      summary {
        cursor: pointer;
        font-weight: 700;
      }

      pre {
        margin: 14px 0 0;
        overflow: auto;
        padding: 12px;
        border-radius: 14px;
        background: #12202f;
        color: #e7eff8;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <h1>Frontend build missing</h1>
      <p>
        The desktop shell can start, but the built React assets were not found under
        <code>frontend/dist</code>.
      </p>
      <p style="margin-top: 12px">
        Build the shell with <code>npm install</code> and <code>npm run build</code>, or point
        the host at a running Vite server with <code>--bridge-start-url http://localhost:5173</code>.
      </p>
      <details>
        <summary>Debug details</summary>
        <pre id="runtime">Waiting for pywebview runtime info...</pre>
      </details>
    </div>
    <script>
      const runtimeNode = document.getElementById("runtime");

      window.addEventListener("pywebviewready", () => {
        if (!window.pywebview?.api) {
          runtimeNode.textContent = "pywebview bridge API is not ready yet.";
          return;
        }

        window.pywebview.api
          .get_runtime_info()
          .then((payload) => {
            runtimeNode.textContent = JSON.stringify(payload, null, 2);
          })
          .catch((error) => {
            runtimeNode.textContent = String(error);
          });
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
