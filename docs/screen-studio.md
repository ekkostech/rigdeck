# Screen Studio (Ice edition)

Open **Screen Studio** in the sidebar. Choose Signature for custom text, a font,
colours and a vertical position. Choose a logo and optional photo/GIF/video
background. Orbit adds moving rim highlights, Pulse animates the title opacity,
and Still holds the design. Video backgrounds and traffic pages may still move
when the decorative effect is Still. Clips last 3–12 seconds.

The initial draft renders locally when the page opens. After editing, choose
**Build preview**. **Send to cooler** uploads the reviewed clip using Rigdeck's
existing uploader and selects only that new design. Older files remain stored.
Legacy GCC text/logo/info overlays are disabled so they cannot cover the new artwork. Manage its playback or remove it
on **Cooler → Screen**. Every render gets a distinct filename so it does not
silently replace an existing clip. Available storage is checked by the uploader.

Drafts persist in `~/.config/rigdeck/studio-draft.json`. Preview/encoded output
is temporary and rebuilt after restart. Missing assets produce a readable error.
The renderer uses Qt's installed fonts and ffmpeg: 320×320, 25fps, H.264 Main
level 3.1, YUV420p, no B-frames, Matroska. Rendering never accesses USB.

## MacDigital search pulse

The Traffic design uses a locally supplied logo and **Google Search Console**
28-day snapshot for `sc-domain:macdigital.ca`. It rotates search clicks,
impressions and search CTR, with a daily impressions chart and the reporting
window end date. The moving rings are decoration, not live traffic activity.

Use **Import analytics snapshot** to update the data. JSON follows the GSC Wizard
`get_site_summary` response: `siteUrl`, `range` (`startDate`, `endDate`, `days: 28`),
`current` (`clicks`, `impressions`, `ctr` as a 0–100 percentage), and optional
`dailyRows` with `impressions`. Other response fields are preserved locally.
The snapshot is stored in `~/.config/rigdeck/traffic-snapshot.json`.

This edition does **not** claim realtime visitors or automatic analytics refresh.
GSC is delayed search data, not total site traffic. Continuous monitoring requires
a persistent authenticated provider and a verified device refresh policy. Do not
refresh the cooler's flash every few seconds. Never commit analytics credentials,
private snapshots or the owner's branding to this public fork.

## Validation

`QT_QPA_PLATFORM=offscreen python -m pytest -q` runs the existing suite plus
renderer/provenance/draft tests. The shared test fixture creates a GUI-capable
Qt application before tests that only need QCoreApplication. Headless screenshots
were inspected for desktop/narrow Studio, Overview, Cooler, GPU and Settings.
The web-oriented static audit cannot inspect QML and is not a substitute for those
native checks.

## Project rotation and Cloudflare live preview

`Projects` renders a continuous loop from locally configured project logos and
28-day Search Console snapshots. `Live projects` is an automatically refreshed
**desktop preview** of Cloudflare request analytics. It rotates the configured
projects with their logos and colours, requests in the rolling 15-minute window,
cache-hit percentage, server errors and transferred bytes. Counts include bots
and assets; they are not unique people. Cloudflare adaptive analytics may be
sampled and ingested with delay. The preview displays elapsed time since the
last successful fetch and explicitly marks stale data after three minutes.

`~/.config/rigdeck/projects.json` holds a list of `{site, name, logo, color,
logoTint?, snapshot}` records. These owner assets and analytics stay outside Git.
`logoTint` recolours a logo while keeping its shape: use it for a dark one-colour
mark that would disappear on a dark screen, for example `"logoTint": "#ffffff"`.
The Cloudflare adapter uses the existing `mac` SSH host and `ekkos-gui-run` to
read `cloudflare-main` inside the Mac vault process. Only aggregate metrics
return to Linux; no credentials are copied or placed in files. Polling is once
per minute while the app runs, without overlapping requests. Missing data appears
unavailable.

### Reading the sight glass

The waterline is the last 15 minutes of requests, oldest minute on the left. The
first and last minutes can be partial because the source window is exactly 15
minutes. Height is logarithmic on one scale shared by every site, so a burst on
one site does not flatten a single request on another. The scale starts at 10
requests a minute, so a quiet portfolio is not drawn as a flood.

A replay raises the water minute by minute and the count climbs through the
recorded minutes to the real total. Droplets are requests, up to 24 per minute;
a minute's droplets launch together because per-minute is the finest timing the
source provides. Replay is labelled with the minute it is showing.

Calm water means no requests. An empty glass means no data. Grey water means the
numbers are over three minutes old, and it does not replay. Turning off **Replay
minute history**, or reduced motion, shows the finished state. Logos never move
or change scale.

### Sending Live projects to the cooler

The cooler only plays clips stored in its flash. **Build preview** turns the
latest fetched numbers into one full rotation, seconds per site × sites long, and
**Send to cooler** stores that clip. It is a snapshot, not a live feed: each site
shows `As of <time>` and the numbers stay until you send another one. Building is
refused when the numbers are missing, over three minutes old or unusable; choose
**Refresh Cloudflare now** and build again. The desktop preview stays live. Nothing
sends to the cooler on a timer, because rewriting its flash every minute would wear
it out. A flash-free live path through the native CPU-name field (command E1) is
untested on the physical display.

## Once-a-day update

`rigdeck studio-daily` keeps the Projects clip current without anyone opening
the app:

1. It runs the command in `~/.config/rigdeck/studio-daily.json`, for example
   `{"command": ["macdigital-search", "all", "--json"]}`. The command prints
   `{"sites": [...]}`, one 28-day Search Console summary per site.
2. Each project in `projects.json` whose site returned usable, newer numbers
   gets them. A site that returned nothing keeps the numbers it had, and its
   card keeps showing their own end date.
3. It builds one Projects clip, stores it as `daily-<date>-<id>.mkv`, makes it
   the only clip playing, and then removes earlier `daily-` clips. Clips with
   any other name are never removed.

The cooler only plays clips stored in its flash, so this is a storage write.
Once a day is a few hundred writes a year. When neither the numbers nor the
look changed since the last send, nothing is written. If the cooler cannot be
reached or has no room, the earlier clip and the earlier numbers stay.

`--dry-run` fetches and builds into `studio-daily-preview/` without touching
the cooler or `projects.json`; `--force` sends even when nothing changed.
Run it from a systemd user timer to make it daily.

## The tank

With a `tank` section in `~/.config/rigdeck/studio-daily.json`, the once-a-day
update builds a different clip: one site's numbers, several in turn, each
surfacing out of a porthole of glowing coolant in the site's colour while the
site's logo turns above it.

    {"command": ["macdigital-search", "all", "--json"],
     "tank": {"project": "macdigital.ca",
              "positions": ["macdigital-search", "positions", "macdigital.ca"],
              "res": 384, "samples": 72}}

`project` names a project in `projects.json` (its `color`, `logo` and
`logoTint` dress the scene). `positions` is optional; with it the clip also
shows how many searches the site appears for, how many on page one and how
many in the top three. The numbers shown are: times shown on Google, the
change against the 28 days before, clicks, and those three.

Each number is a 7-second segment rendered by Blender (`rigdeck/gui/tank_scene.py`),
about five minutes of graphics-card time at the default size. Rendered segments
are kept in `~/.cache/rigdeck/tank/` and reused while the number, colour and
logo are unchanged, so a typical day renders only what moved. Segments unused
for two days are dropped. Labels are added afterwards by `rigdeck/gui/tank.py`,
over a darker depth in the liquid that keeps them at 4.5:1 against anything
the liquid does; a changed label never needs a new render.

Blender must be installed (`pacman -S blender`). `--dry-run` works as for the
Projects clip. In the app, the **Tank** preset in Screen Studio builds the same
clip on request and sends it with Send to cooler.
