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
logoPlate?, snapshot}` records. These owner assets and analytics stay outside Git.
The Cloudflare adapter uses the existing `mac` SSH host and `ekkos-gui-run` to
read `cloudflare-main` inside the Mac vault process. Only aggregate metrics
return to Linux; no credentials are copied or placed in files. Polling is once
per minute without overlapping requests. Missing data appears unavailable.

Live hardware output remains under verification; the app deliberately disables
video upload in Live projects. It does not silently convert a live preview into
a permanently stale video, nor repeatedly rewrite the cooler flash. The known
native CPU-name field can be updated with command E1, but on-screen behavior
needs physical verification. The owner was asked to observe a bounded native
mode-2 test; original display settings were restored afterward.

The live canvas now uses minute bars on a shared linear scale across the fetched
portfolio. The first and last buckets can be partial minutes because the source
window is exactly 15 minutes. A sweep explicitly labelled REPLAY follows those
buckets and displays their local-clock minute and request count. It is not a
per-request event stream. The inner arc maps cache share to 0–100%; totals,
5xx errors and bandwidth remain visible. Zero windows, missing data, stale
data and reduced motion stop the sweep. Logos never move or change scale.
