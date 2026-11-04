---
version: alpha
name: Rigdeck Ice
description: A native hardware instrument panel with a circular screen studio.
colors:
  background: "#090f17"
  panel: "#111c28"
  raised: "#1b2b3b"
  text: "#edf5fc"
  muted: "#a0b4c8"
  border: "#2b4053"
  primary: "#89dcff"
  on-primary: "#091723"
typography:
  sans:
    fontFamily: "Adwaita Sans, sans-serif"
  mono:
    fontFamily: "Adwaita Mono, monospace"
rounded:
  DEFAULT: "10px"
spacing:
  page-max: "1152px"
  page-gutter: "24px"
  narrow-gutter: "16px"
components:
  button:
    background: "{colors.raised}"
    color: "{colors.text}"
    border: "{colors.border}"
  card:
    background: "{colors.panel}"
  input:
    color: "{colors.muted}"
  navigation: {}
  dialog: {}
---

# Rigdeck Ice

## Overview

A precision instrument panel inspired by the WATERFORCE ICE cooler. The owner selected graphite and frost blue. This is a native Linux product for hardware monitoring and control, not a marketing site. Keep dense sensor information readable. The signature element is the circular LCD canvas; decorative motion belongs inside that preview, not across the settings UI.

Runtime tokens in `rigdeck/gui/theme.py` are canonical. This document mirrors the Ice palette. Existing light, dark and custom palettes remain supported. UI language is English; Qt handles font fallback and localized numbers. This fork keeps the upstream device protocols.

## Colors

Graphite background, blue-black panels, raised controls, frost accent and pale text define the hierarchy. Muted text remains readable. Borders separate surfaces without heavy shadows. Selected navigation uses a translucent accent; primary actions use dark ink on frost. Shared live, warning and error tokens retain distinct semantic colours. Colour never replaces an error message or connection label.

## Typography

Adwaita Sans is the installed native face, with Qt's fallback when unavailable. Page titles are 30px, panel headings 16px, controls 13px and supporting details 12px. Adwaita Mono at 32px makes the main sensor readings easy to scan. The wordmark alone uses spaced capitals. User-entered LCD text supports installed fonts and is fitted into the circular safe area.

## Layout

PageScroll owns vertical scrolling and caps content at 1152px. Gutters are 24px, reducing to 16px below 700px. The 224px sidebar becomes 64px below 760px; settings stays pinned. Studio uses two columns above 820px of content width and stacks below. The top bar is 64px. Hardware metrics retain their adaptive grid. Avoid horizontal page scrolling.

## Elevation & Depth

App surfaces use tonal layering and fine borders. The LCD animation alone uses concentric bevels, logo extrusion and moving specular arcs. Those effects are decorative and do not represent traffic or hardware state. Charts show source values without fabricated movement.

## Shapes

Cards and shared controls use a 10px radius. Controls are 38px tall, sidebar targets 44px. The circular preview is a deliberate hardware-shaped exception. Lucide icons remain the canonical icon set.

## Components

Shared QML primitives in `rigdeck/gui/qml/RigDeck` own buttons, fields, panels, navigation and metrics. Focus uses visible accent borders; hover is tonal; disabled controls are dimmed and non-interactive. Busy rendering preserves button geometry, disables edits and reports status. Native Qt file and colour dialogs provide keyboard operation. Error banners persist until editing or retry. Toasts report device actions through the existing app state.

Reduced motion freezes rendered previews on their poster and stops decorative motion in live previews. Signature and Traffic start offline and remain useful without a cooler. An edited design invalidates the send action until a new preview is built. Uploaded clips reuse the existing hardware backend and its connection/progress/error handling.

## Do's and Don'ts

- Use shared tokens and controls across hardware pages.
- Keep unknown sensor values as unavailable, never zero or fabricated healthy states.
- Keep the source, reporting window and snapshot status visible for analytics.
- Do not call search clicks visitors or imported snapshots live traffic.
- Do not upload on every edit or use repeated flash writes as a streaming protocol.
- Do not add animations to normal control-panel surfaces.


## Project display variants

Each locally configured project supplies its real logo and accent colour within
the shared circular bezel. A light logo plate is permitted for dark artwork
such as Mary Cleaning's mark. Wide logos preserve their aspect ratio. Project
controls hide single-logo and accent choices that would be overridden by the
rotation. Live metrics show the source window and fetch age; decorative motion
never implies fresh events.

Logos stay fixed in position and scale; no breathing or bobbing. Motion belongs to the surrounding bezel.


## Cloudflare traffic replay — design direction

Subject: six monitored websites on a circular 320px instrument; the job is to
show the shape of recent request traffic and the cache share at a glance.

Tokens: graphite #09121b, track #263b4b, frost #d4f3ff, muted #8da9b9,
cache mint #79dcc5, error coral #ff806f. Site accents retain their brand meaning.
Nimbus Sans Narrow carries the stable request total; Adwaita Sans labels the
site; Adwaita Mono gives times and measured units consistent spacing.

Layout: minute bars wrap 270 degrees around a fixed logo and a stable metric
stack; an inner mint arc shows cache percentage. The lower opening is a replay
caption and fetch age. A highlighted minute follows recorded time, not wall time.

    [ measured minute bars / shared linear scale ]
    [ cache-share arc / fixed brand mark         ]
    [ total requests / cache / 5xx / bandwidth   ]
    [ replay minute + its requests / fetch age  ]

Critique: discarded the decorative spinning arcs and three-number carousel.
A simulated particle stream would imply request-level timing we do not have;
minute history uses the actual granularity available. A shared scale makes
quiet and busy sites distinguishable. Zero-minute ticks are baseline markers,
not positive bars. Empty, stale and unavailable data do not animate activity.
Reduced motion stops the replay marker while keeping measured content visible.
