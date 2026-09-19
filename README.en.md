# Steam Game Picker

**English** | [简体中文](README.md)

[![tests](https://github.com/collinszheng/SteamGamePicker/actions/workflows/tests.yml/badge.svg)](https://github.com/collinszheng/SteamGamePicker/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> Paste your Steam ID or profile URL, load your library, hit one button — and let it pick what you play tonight.

A small Windows 10/11 desktop tool for the "hundreds of games, no idea what to play" problem.
Plain Tkinter UI, no Steam login required — it only reads public data through Steam's public Web API.
The interface is available in **Chinese and English** (Chinese by default).

## Download

**➡️ [Download the latest installer](https://github.com/collinszheng/SteamGamePicker/releases/latest)** (`SteamGamePicker_Setup.exe`, ~21 MB)

Double-click to install — **no administrator rights needed**. A desktop shortcut is optional, and the
uninstaller asks whether to keep your config and cache. On first launch you'll be guided through
entering a Steam Web API Key ([get one here](https://steamcommunity.com/dev/apikey), free).

To run from source instead, see [Quick start](#quick-start-from-source).

## Features

| Feature | Details |
| :--- | :--- |
| Identity parsing | Accepts a 17-digit SteamID64, a `/profiles/` URL, an `/id/` custom name, or a bare custom name |
| Library loading | Fetched on a background thread so the UI never freezes; shows total count and how many are in the pool |
| Local cache | Library snapshot + details cache (7 days by default); **instant startup and picking works offline** |
| Range filters | “All games” / “Never played” / “Barely played” (the last two **can be combined**, union semantics); individual games can also be unchecked in the list |
| Picking animation | 1.8 s rolling deceleration, the winner locks in green and bold; the result is drawn uniformly from the current selection |
| Result panel | Cover, summary, genres, release date, Metacritic score and price (list price only, never the discounted one) |
| Error messages | Clear Chinese/English messages that distinguish “profile is private”, “invalid key”, “library is empty”, “too many requests” and more |
| UI language | **Chinese / English**, switchable in Settings (Chinese by default, applied instantly — no restart) |
| Certificate fallback | If certifi can't verify the chain, it retries once against the OS trust store — **certificate verification is never disabled** |

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
| `Esc` | Close the settings window / cancel an ongoing load |

## Running the tests

```powershell
python -m pytest        # 438 tests
```

The suite covers pure logic (ID parsing, preset computation, cache TTL), the network layer contract
(offline samples reproduce Steam's responses and error codes), UI interaction, performance budgets,
the exception matrix and the certificate fallback path — everything runs offline.

## Building the installer

```powershell
python -m PyInstaller packaging\SteamGamePicker.spec --noconfirm   # produces dist\SteamGamePicker.exe
ISCC.exe packaging\installer.iss                                   # produces dist\SteamGamePicker_Setup.exe (needs Inno Setup 6)
```

The installer installs per-user without admin rights, offers an optional desktop shortcut and a start
menu entry, can launch the app when done, supports silent install (`/VERYSILENT`), and asks on uninstall
whether to keep your config (default: keep).

Self-check for a packaged build:

```powershell
.\dist\SteamGamePicker.exe --selftest --live --report .\dist\selftest.json
```

> `dist/` and `build/` are excluded by `.gitignore`, so build artifacts are not committed.
> End-user installers are published on the [Releases](https://github.com/collinszheng/SteamGamePicker/releases) page.

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
│  ├─ config.py             Config I/O (atomic writes, corruption recovery)
│  ├─ worker.py             Background thread + queue + cancellation tokens
│  ├─ i18n.py               Chinese and English message tables
│  ├─ state.py              State machine and widget enable/disable mapping
│  └─ ui/                   Main window, animation, settings dialog, theme
├─ tests/                   438 pytest cases (including Steam response fixtures)
├─ packaging/               PyInstaller spec and Inno Setup script
├─ tools/                   Live-check and icon generation scripts
└─ docs/                    PRD, development plan, acceptance record
```

## Documentation

| Document | Contents |
| :--- | :--- |
| [Product requirements (PRD)](docs/PRD.md) | Goals, page structure, per-module data and actions, local data rules, scope, acceptance criteria |
| [Development plan](docs/DEV_PLAN.md) | M0–M8 task breakdown, interface contracts, schedule and outcome |
| [Acceptance record](docs/ACCEPTANCE.md) | AC-01 ~ AC-52 with evidence, documented deviations and the pending list |

> The three documents above are currently written in Chinese.

## Privacy and security

- Talks only to Steam's public endpoints, **never asks you to log in**, and never buys, downloads or launches games
- The API Key is stored on this machine only (`%APPDATA%\SteamGamePicker\config.json`) — never uploaded, never hardcoded, never bundled into the installer
- Logs are redacted: a full API Key never reaches the log file
- Everything is HTTPS, and network problems are never worked around by disabling certificate verification

## License

Released under the [MIT License](LICENSE): free to use, modify and distribute, **including commercially**,
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

The packaging tool **PyInstaller** is GPL-2.0-or-later **with a special exception** that explicitly
allows building and distributing non-free programs (including commercial ones), so this project's build
artifacts (`SteamGamePicker.exe` / the installer) are not subject to the GPL. The installer is produced
by Inno Setup, whose license permits free use (see [jrsoftware.org](https://jrsoftware.org/) for the
commercial terms).
