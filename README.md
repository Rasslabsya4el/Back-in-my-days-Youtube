# Back in my days Youtube

Back in my days Youtube is a Windows desktop app for saving YouTube audio or video with a queue, simple format choices, and a visible output folder.

![Back in my days Youtube app screenshot](docs/assets/back-in-my-days-youtube-ui.png)

## Download

Get the current Windows build from [GitHub Releases](https://github.com/Rasslabsya4el/Back-in-my-days-Youtube/releases/latest).

| Option | Pick this if | What to expect |
| --- | --- | --- |
| Installer | You want a normal Windows setup with shortcuts and app data stored outside the install folder. | Installs `Back in my days Youtube`, keeps writable app data under `%LOCALAPPDATA%\Back in my days Youtube`, and writes installer/startup diagnostics to `C:\ProgramData\Back in my days Youtube\logs\debug.log`. |
| Portable | You want to unzip and run it without installing. | Extract the ZIP first, keep `Back in my days Youtube.exe` next to `_internal\`, and the app will create `runtime\`, `output\`, and `temp\` next to the executable. |

If Windows SmartScreen appears, use `More info` -> `Run anyway`.

## How to use

1. Download the `Installer` or `Portable` build from [Releases](https://github.com/Rasslabsya4el/Back-in-my-days-Youtube/releases/latest).
2. Install it or extract the ZIP to a normal folder, then start `Back in my days Youtube`.
3. Paste a YouTube link and click `Add to queue`.
4. Choose where to save files, then pick `Audio` or `Video` and the quality you want.
5. Click `Start download` for one item or `Download all queued` for the whole queue.
6. Open the saved folder from the app after the item finishes.

## What gets saved and where are logs

- Downloads go to the app's current output folder. By default that is `<portable-folder>\output` for the portable build and `%LOCALAPPDATA%\Back in my days Youtube\output` for the installer build. If you change the folder in the app, new downloads go to the folder you picked for the current session.
- Working files and queue state live alongside that writable app data root in `runtime\` and `temp\`.
- Installer and startup diagnostics append to `C:\ProgramData\Back in my days Youtube\logs\debug.log`.
- The installed app folder also contains `debug-log-path.txt`, which points to the real debug log location on that PC.
- If you report a problem, include the YouTube link you tried, whether you used `Installer` or `Portable`, what happened on screen, and the contents of `debug.log` or `debug-log-path.txt`.

## Support

- Releases: [github.com/Rasslabsya4el/Back-in-my-days-Youtube/releases](https://github.com/Rasslabsya4el/Back-in-my-days-Youtube/releases)
- Issues: [github.com/Rasslabsya4el/Back-in-my-days-Youtube/issues](https://github.com/Rasslabsya4el/Back-in-my-days-Youtube/issues)

## Technical runbook

Build, packaging, local start, smoke checks, and bridge/runtime notes were moved to [docs/technical-runbook.md](docs/technical-runbook.md) so this page stays focused on the end-user flow.
