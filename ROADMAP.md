# Roadmap

## Guiding decisions

- **libtorrent does the protocol work.** We never parse BitTorrent messages
  ourselves. Our code handles configuration, persistence, the user interface
  and policy (for example, when to stop seeding).
- **Pin `libtorrent>=2.0.15,<2.1`.** These are the PyPI wheels the code was
  tested on. The 2.0.11 Windows wheel needs OpenSSL 1.1 DLLs that it doesn't
  include; 2.0.13 and later link OpenSSL statically. libtorrent 2.1 changes
  the API, so moving to it is a deliberate task (see Phase 4).
- **Keep one engine and add front-ends on top of it.** `engine.Engine` is the
  only module that talks to libtorrent. The terminal UI, a daemon and a web UI
  all drive that one class.
- **Resume data is the source of truth.** One `.resume` file per torrent, written
  atomically. The client keeps no other database. (`settings.json` holds
  preferences and `window.json` the window layout; neither holds torrents.)

## Phase 0: MVP ✅

- [x] Add `.torrent` files and magnet links
- [x] Live status table: progress, rates, peers, ratio, ETA, recent events
- [x] Seeding after completion, with an optional `--seed-ratio` stop
- [x] DHT, µTP, LSD, PEX, UPnP/NAT-PMP, encryption policy
- [x] Global download/upload rate limits
- [x] Resume data: at add time, on metadata, on finish, every 60 s and at shutdown
- [x] DHT routing table saved between runs
- [x] Clean shutdown on Ctrl+C and SIGTERM
- [x] `list` / `remove` commands that work without starting the client
- [x] Offline end-to-end tests (loopback seeder and leecher)

**Known gaps**
- Not yet tested against the public swarm. The build sandbox blocks UDP, so DHT
  and µTP were only tested on loopback. Do a manual run with a real magnet
  before calling this "done".
- The rest apply to terminal mode only; the desktop window covers them:
  - You can't add or remove torrents while it's running: restart with new
    sources instead.
  - `avilys remove` only forgets the torrent. It never deletes downloaded data.
  - There's no per-torrent save path or file selection.

## Phase 1: Desktop GUI (direction A, "classic") ✅ first version

Chosen from two mockups: the dense, light layout with toolbar, status
sidebar, table and detail tabs. Built with PySide6 (Qt), in the same process as
the engine.

- [x] Toolbar: add .torrent, add magnet, resume, pause, remove (optionally
      deleting files), filter box, settings
- [x] Status sidebar with live counts; sortable table with progress bars
- [x] Detail tabs: General, Files (with priorities / skip), Peers (µTP/TCP,
      encryption, source), Trackers
- [x] Drag and drop of `.torrent` files and magnet links
- [x] Settings dialog that applies live and is saved to `settings.json`
- [x] Clean shutdown on window close; offscreen GUI test

## Phase 1b: Installers ✅ first version

- [x] Windows: PyInstaller bundle plus an Inno Setup installer (per-user, no
      admin). It has optional magnet and `.torrent` associations, Start menu and
      desktop shortcuts, and an uninstaller.
- [x] Linux: an AppImage (built on Ubuntu 22.04 for glibc compatibility) with a
      `.desktop` entry for `magnet:` and `.torrent`.
- [x] Single instance: a second launch hands its links to the open window.
- [x] CI builds both on every push and self-tests each one. The Windows job
      silently installs, checks the magnet registration, runs the installed app
      and uninstalls. A `v*` tag publishes both to a GitHub Release.
- [ ] Code signing for Windows (SmartScreen warns about unsigned installers
      until they build up a reputation). This needs a certificate, and is your call.
- [x] Update check: once a day, compare with the latest GitHub Release and offer
      to open its download page (Settings → General → Updates).
- [ ] Smaller bundle: trim unused Qt modules and ICU data (the AppImage is about 60 MB).
- [ ] Optional `.deb` / Flatpak for Linux users who prefer them.

## 0.2.0: Everyday polish ✅

The goal: a nice, simple torrent client that works.

- [x] **System tray:** closing the window keeps downloading in the tray. The
      tray menu has Show, Resume all, Pause all and Quit. Without a tray,
      closing the window quits.
- [x] **Notification when a download finishes.** It's only shown for torrents
      seen downloading in this session, so a restart or re-check stays quiet.
- [x] **Add dialog:** pick the save folder and which files to download before
      starting, with the selected size and free space shown. It can be turned
      off.
- [x] **Duplicate protection:** adding a torrent that's already in the list
      gives a clear message.
- [x] **Dark theme:** light, dark, or follow the system, switching live.
- [x] Padding files (an internal detail of some torrents) are hidden in the
      Files tab and the add dialog.
- [x] Engine fix: events for a torrent removed moments earlier no longer stop
      the processing of other events.

## 1.0: A client that can replace Tixati ✅

The goal is a usable, good-looking client that isn't overengineered.

- [x] Choose files for magnet links when their file list arrives (nothing
      downloads before the choice)
- [x] Peer countries with flags (DB-IP Lite, refreshed monthly; bundled in
      the installers)
- [x] Pieces tab and a Speed tab with a 5-minute graph
- [x] Right-click actions: open folder, move, copy magnet link, download in
      order, per-torrent speed limits, check files again, announce now
- [x] Tracker editing
- [x] Slow mode (alternative limits) with a status bar toggle and daily
      schedule
- [x] Seeding rules (ratio and/or time) and queue limits
- [x] Watch folder
- [x] Bind to a network adapter (VPN kill-switch style)
- [x] IP blocklists
- [x] Settings in tabs
- [x] The full test suite runs on Windows as well as Linux

## 1.1 ✅

**Small things you notice daily**
- [x] Remember the window: size, position, column widths and sort order (and
      the detail pane's height and open tab)
- [x] Keep the computer awake while a download is running
- [x] Start with the system, minimised to the tray (optional)
- [x] A separate folder for unfinished downloads; files move to the save
      folder when complete. The destination is kept in the torrent's resume
      file.
- [x] Port check: a status bar indicator showing whether Avilys is reachable
      from outside. It is worked out from incoming connections, with no
      outside service.

**Torrent errors**
- [x] Show a torrent's error (disk full, no permission, missing files) in the
      table and the General tab, with its own sidebar filter, instead of only
      in the event log, and a "Try again" button
- [x] A notification when a torrent stops because of an error

**Lithuanian translation**
- [x] Make every string in the window translatable
- [x] Lithuanian translation, with a language choice in Settings → General
      (system, English, Lietuvių)
- [x] Translate the installer and the `.desktop` entry
- [x] A test that fails when a string is left untranslated

**Anonymous mode**
- [x] A switch in Settings → Privacy that hides the client name and version
      from peers and trackers, applied live. libtorrent's `anonymous_mode`
      alone leaves the client's fingerprint in the peer id, so Avilys drops
      that too.
- [x] A test that checks what the other side sees with it on

**Left over from 1.1**
- The Lithuanian wording needs a read-through by a native speaker.
- Country names in the Peers tab are still English.
- A new language applies at the next start, not live.
- Keeping awake and starting with the system were tested on Linux with
  stand-ins and on Windows in CI; neither has been tried on a real desktop.
- Starting with the system isn't offered on macOS (there is no macOS build yet).

## 1.x candidates

- RSS feeds with simple download rules
- Creating torrents, including v2 and hybrid torrents
- Categories/labels, each with its own save folder
- [x] An "About" window

The update check and the smaller download are listed under Phase 1b.

## Parked

Good ideas that aren't essential for a simple client, kept for later:

- **Download safety:** a quarantine folder for new downloads, warnings about
  disguised files (such as `movie.mp4.exe`), an antivirus scan, an opt-in
  VirusTotal hash lookup, and "Open in sandbox" (Windows Sandbox or
  Sandboxie-Plus on Windows, bubblewrap on Linux).
- **Phone access:** use a phone as a remote control for a computer running
  Avilys (needs Phase 2). A full iOS client is possible only in the EU through
  alternative app stores, and only while the app is open.

## Phase 2: Daemon and remote control

Goal: run the client headless on a server or NAS and control it from elsewhere.

1. **Daemon mode.** `avilys daemon` runs the engine with no UI and logs to a file.
2. **Control API.** A JSON API over a Unix socket, then HTTP (FastAPI or
   aiohttp) with token auth. Endpoints: add, remove, pause, resume, list,
   details and settings.
3. **Thin CLI client.** `avilys add/ls/pause` talk to the daemon (or to the
   open GUI window) when one is running, and fall back to standalone mode otherwise.
4. **Web UI.** One static page served by the daemon.
5. **systemd unit and Dockerfile.**

## Phase 3: Power features

These are mostly libtorrent switches plus some UI work.

- [x] Sequential download (for previewing media)
- [x] Per-torrent rate limits
- [x] IP filter / blocklist import
- [x] Binding to a VPN interface
- [x] Moving downloads to another folder
- [x] Notifications when a torrent finishes
- [ ] Proxy support (SOCKS5 or HTTP)
- [ ] An "on finish" hook script

Creating torrents, labels and RSS are listed under "1.x candidates".

## Phase 4: Hardening

- [x] Run the full `pytest` suite on Windows too
- Use `post_torrent_updates()` / `state_update_alert` instead of polling
  `status()` for each torrent, so status updates scale to hundreds of torrents
- Fuzz and test corrupt resume files and `.torrent` files
- Decide whether to move to libtorrent 2.1, and which API changes that needs
- Packaging: `pipx install avilys` for the terminal version

## Open questions for you

1. **Windows code signing:** buy a certificate, use Azure Trusted Signing, or
   ship unsigned for now (users click "More info → Run anyway" once).
