# <img src="docs/evidence/icon-256.png" width="40" alt="app icon"> Steam Game Picker

**English** | [简体中文](README.md)

[![tests](https://github.com/collinszheng/SteamGamePicker/actions/workflows/tests.yml/badge.svg)](https://github.com/collinszheng/SteamGamePicker/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Hundreds of games in your library and no idea what to play tonight?** Paste your Steam ID or profile URL,
hit one button, and get tonight's game picked at random.

A small Tkinter desktop app for Windows: it **never logs into your Steam account**, never buys or launches
anything, and only reads public data through Steam's public Web API. Bilingual UI, playtime-based filters,
pick history, and offline-friendly caching.

## Download

**➡️ [Download the latest installer](https://github.com/collinszheng/SteamGamePicker/releases/latest)** (`SteamGamePicker_Setup.exe`, ~21 MB)

Double-click to install — **no administrator rights needed**. The wizard ships in **Simplified Chinese (default)
and English**, and the app starts in whichever you picked. On first launch you'll be guided through entering
a Steam Web API Key ([get one here](https://steamcommunity.com/dev/apikey), free).
The installer is not code-signed: if SmartScreen warns you, choose "More info" → "Run anyway".

To run from source instead, see [Quick start](#quick-start-from-source).

## Features

- **Identity parsing** — accepts a 17-digit SteamID64, a `/profiles/` URL, an `/id/` custom name, or a bare custom name
- **Library loading** — fetched on a background thread so the UI never freezes; shows the total and how many are in the pool
- **Range filters** — "All games" / "Never played" / "Barely played"; the last two **can be combined** (union),
  and individual games can be unchecked in the list (excluded rows are dimmed)
- **Picking animation** — 1.8 s rolling deceleration, the winner locks in green and bold; the result is drawn
  **uniformly** from the current selection
- **Result panel** — cover, summary, genres, release date, Metacritic score and price (list price only, never the
  discounted one); the panel has a **fixed height**, so the window no longer jumps on every pick
- **Pick history** — keeps the last **10** picks in a separate window; double-click an entry to open that game's
  details, clear it with one button
- **Local cache** — library snapshot + details cache (7 days by default): **instant startup and picking works offline**
- **UI language** — Chinese / English, **defaults to your system language**, applied instantly from Settings (no restart)
- **Window size** — defaults to **680 × 880**, with 800 × 1100 / 1100 × 800 in a Settings dropdown; size and position
  are remembered, and the window plus every dialog opens centred
- **Error messages** — clear Chinese/English messages that distinguish "profile is private", "invalid key",
  "library is empty", "too many requests" and more
- **Certificate fallback** — if certifi can't verify the chain, the OS trust store is used for one retry;
  **certificate verification is never disabled**
- **Small** — single-file exe around **20 MB**, installer around **21 MB**; 575 tests, all offline

## Tech stack

| | |
|---|---|
| Language / UI | Python 3.12 · Tkinter/ttk (hand-drawn Steam dark theme on the `clam` theme) |
| Network / imaging | requests · Pillow · optional truststore (certificate fallback) |
| Architecture | pure-logic layer (`steamid`/`pool`/`config`/`cache`) never imports tkinter; background thread + queue + cancel token |
| Data | `%APPDATA%\SteamGamePicker\`: `config.json` (atomic writes) · `history.json` · library snapshot and details cache |
| Packaging | PyInstaller (onefile, windowed, with a version resource) · Inno Setup 6 (non-admin install) |
| Tests | pytest, 575 cases, fully offline (including Steam response fixtures, widget geometry and contrast checks) |

## Requirements

- Windows 10 / 11 (64-bit)
- Python 3.10+ (only needed to run from source)
- A Steam Web API Key: [apply here](https://steamcommunity.com/dev/apikey) (free, first launch walks you through it)

## Quick start (from source)

```powershell
pip install -r requirements.txt
python main.py
```

First launch opens a setup dialog for the API Key; after saving, paste your Steam profile URL to load the library.
Configuration lives in `%APPDATA%\SteamGamePicker\config.json`.

## Keyboard shortcuts

| Key | Action |
| :--- | :--- |
| `Enter` (in the input field) | Load the library |
| `Space` | Pick / pick again (keeps its native meaning inside the list or on buttons) |
| `Enter` (list focused) | Toggle the checkmark of the current row |
| `F5` | Refresh the library |
| `Ctrl` + `,` | Open Settings |
| `Esc` | Close Settings / cancel a running load |

## Running the tests

```powershell
python -m pytest        # 575 tests
```

They cover pure logic (ID parsing, preset evaluation, cache TTL), the network contract (offline fixtures that
reproduce Steam's responses and error codes), UI interaction and geometry, performance budgets, the error matrix
and the certificate-fallback path — all offline, with no network or real account needed.

## Packaging and self-check

```powershell
python -m PyInstaller packaging\SteamGamePicker.spec --noconfirm   # → dist\SteamGamePicker.exe
ISCC.exe packaging\installer.iss                                   # → dist\SteamGamePicker_Setup.exe (needs Inno Setup 6)
.\dist\SteamGamePicker.exe --selftest --live --report .\dist\selftest.json
```

The installer installs without administrator rights, ships a bilingual wizard, offers an optional desktop
shortcut, adds a Start-menu entry, can launch the app when done, supports silent install (`/VERYSILENT`),
and asks before removing your settings on uninstall (kept by default).

The app icon is generated by a script, so changing colours or the motif means re-running it (no hand-drawing):

```powershell
python tools\make_icon.py      # rewrites assets\app.ico and refreshes docs\evidence\icon-preview.png
```

> Installers are published on the [Releases](https://github.com/collinszheng/SteamGamePicker/releases) page;
> `dist/` and `build/` are ignored by `.gitignore`, so build output never enters the repository.

## Project layout

```
SteamGamePicker/
├─ main.py                  Entry point (includes the --selftest packaging check)
├─ app/
│  ├─ steamid.py            Identity input parsing (pure functions)
│  ├─ steam_api.py          Steam Web API wrapper and error classification
│  ├─ trust.py              Certificate fallback to the OS trust store
│  ├─ pool.py               Range filters, pickable pool, uniform random (pure functions)
│  ├─ cache.py              Library snapshot / details / cover cache
│  ├─ history.py            Pick history (last 10 picks)
│  ├─ language_marker.py    Language chosen at install time (registry marker, consumed on first run)
│  ├─ config.py             Config I/O (atomic writes, corruption recovery, legacy window-size migration)
│  ├─ worker.py             Background thread + queue + cancellation tokens
│  ├─ i18n.py               Chinese and English message tables + system-language detection
│  ├─ state.py              State machine and widget enable/disable mapping
│  └─ ui/                   Main window, animation, settings/history dialogs, theme, title bar
├─ tests/                   575 pytest cases (including Steam response fixtures)
├─ packaging/               PyInstaller spec and Inno Setup script (with the Chinese language file)
├─ tools/                   Live-check and icon generation scripts
└─ docs/                    The single folder for development docs: PRD, plan, acceptance record
```

## Documentation

| Document | Contents |
| :--- | :--- |
| [Product requirements (PRD)](docs/PRD.md) | Goals, page structure, per-module data and actions, local data rules, scope, acceptance criteria |
| [Development plan](docs/DEV_PLAN.md) | M0–M8 task breakdown, interface contracts, schedule and outcome |
| [Acceptance record](docs/ACCEPTANCE.md) | AC-01 ~ AC-69 with evidence, documented deviations and the pending list |
| [Changelog](CHANGELOG.md) | What was added, changed and fixed in every release |

## Privacy and security

- Only Steam's public endpoints are used — **no Steam login**, no purchasing, downloading or launching of games
- The API Key stays on this machine in `%APPDATA%\SteamGamePicker\config.json`: never uploaded, never hardcoded,
  never bundled into the installer
- Logs are redacted automatically: a full API Key never reaches the log file
- Everything is HTTPS; when certificate verification fails the OS trust store is used for one retry —
  verification is **never** turned off to work around a network problem
- All data stays local: no usage information is collected or reported

## License

Released under the [MIT license](LICENSE): free to use, modify and redistribute, **including commercially**,
as long as the copyright notice and license text are kept in copies or substantial portions.

Copyright (c) 2026 collinszheng.

### Third-party dependencies

All runtime dependencies use permissive licenses:

| Dependency | License |
| :--- | :--- |
| requests | Apache-2.0 |
| Pillow | MIT-CMU |
| truststore (optional) | MIT |
| urllib3 / charset-normalizer | MIT |
| certifi | MPL-2.0 |
| idna | BSD-3-Clause |

**PyInstaller** is GPL-2.0-or-later **with a special exception** that explicitly permits building and
distributing non-free programs (including commercial ones) with it, so this project's build output
(`SteamGamePicker.exe` / the installer) is not subject to the GPL. The installer is produced by Inno Setup,
whose license allows free use (commercial terms at [jrsoftware.org](https://jrsoftware.org/)).
