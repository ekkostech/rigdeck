"""Once-a-day cooler update: fresh Search Console numbers, one new clip, the old one removed.

The cooler only plays clips stored in its flash, so numbers reach the screen by
sending a new clip. Once a day is a few hundred writes a year; this never runs
more often than the numbers change, and skips the send when nothing changed.

    rigdeck studio-daily              fetch, build, send, remove yesterday's clip
    rigdeck studio-daily --dry-run    fetch and build only; nothing touches the cooler
    rigdeck studio-daily --force      send even when the numbers have not changed

Numbers come from the command in ~/.config/rigdeck/studio-daily.json, for example
{"command": ["macdigital-search", "all", "--json"]}. It must print
{"sites": [<28-day Search Console summary>, ...]} as JSON.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PREFIX = 'daily-'  # only clips this job made carry it, and only those are ever removed
DESIGN = 1         # bump when the picture changes, so the next run sends it


def root() -> Path:
    from . import studio
    return studio.ROOT


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=1))
    temp.replace(path)


def fetch(command, timeout=120) -> dict:
    """Run the numbers command; return {siteUrl: summary} for the sites it could read."""
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise ValueError('Set "command" in studio-daily.json to the program that prints the numbers, as a list.')
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ValueError(f'The numbers command was not found: {command[0]}')
    except subprocess.TimeoutExpired:
        raise ValueError(f'The numbers command took longer than {timeout} seconds.')
    if r.returncode:
        raise ValueError('The numbers command failed: ' + (r.stderr.strip() or f'exit {r.returncode}')[-300:])
    try:
        sites = json.loads(r.stdout)['sites']
        if not isinstance(sites, list): raise TypeError
    except (ValueError, KeyError, TypeError):
        raise ValueError('The numbers command did not print {"sites": [...]} as JSON.')
    return {s['siteUrl']: s for s in sites if isinstance(s, dict) and isinstance(s.get('siteUrl'), str)}


def refresh(projects, summaries):
    """Put each site's fresh numbers in place. A site without usable new numbers keeps
    the ones it had, which stay labelled with their own dates on the screen."""
    from .studio import check_stats
    updated, kept = [], []
    for p in projects:
        name = p.get('name', p['site'])
        site_url = (p.get('snapshot') or {}).get('siteUrl') or 'sc-domain:' + p['site']
        fresh = summaries.get(site_url)
        try:
            if fresh is None: raise ValueError('no numbers returned')
            check_stats(fresh)
            old_end = ((p.get('snapshot') or {}).get('range') or {}).get('endDate', '')
            if fresh['range']['endDate'] < old_end: raise ValueError('older than the numbers already shown')
            p['snapshot'] = fresh
            updated.append(name)
        except (ValueError, KeyError, TypeError) as e:
            kept.append((name, str(e)))
    return updated, kept


def fingerprint(projects, values) -> str:
    """Changes exactly when the picture would: the numbers, their dates, the look."""
    shown = [[p.get('name'), p.get('logo'), p.get('color'), p.get('logoTint'),
              (p.get('snapshot') or {}).get('range'), (p.get('snapshot') or {}).get('current'),
              [r.get('impressions') for r in (p.get('snapshot') or {}).get('dailyRows', [])]] for p in projects]
    look = {k: values.get(k) for k in ('color', 'background', 'effect', 'duration', 'font')}
    return hashlib.sha256(json.dumps([DESIGN, look, shown], sort_keys=True).encode()).hexdigest()


def build(projects, values, folder) -> str:
    from PySide6.QtGui import QGuiApplication
    from .studio import render_projects, validate
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QGuiApplication.instance() or QGuiApplication([])  # fonts and painting need one
    missing = [p.get('name', p['site']) for p in projects if not p.get('snapshot')]
    if missing:
        raise ValueError('No numbers yet for: ' + ', '.join(missing))
    return render_projects(validate({**values, 'media': '', 'logo': ''}), folder, projects)


def send(path: str, name: str, open_cooler=None):
    """Store the clip, show only it, then remove earlier clips this job made."""
    from ..modules.waterforce import add_to_carousel, delete_media, media
    from ..modules.waterforce.device import Cooler
    data = media.convert(path)
    with (open_cooler or Cooler)() as c:
        if name in c.list_media():
            raise ValueError(f'{name} is already on the cooler.')
        if len(data) > c.storage_free_kb() * 1024:
            raise ValueError('Not enough space on the cooler for the new clip.')
        c.upload_media(data, name)
        screen = add_to_carousel(c, name)
        screen.write(c, screen.files, [name])
        c.send(b'\xc0\x00\x00\x00')  # no stock text, logo or readouts over the clip
        c.save()
        removed = []
        for old in [f for f in screen.files if f.startswith(PREFIX) and f != name]:
            screen = delete_media(c, old, screen)
            removed.append(old)
        return removed, c.storage_free_kb()


def run(dry_run=False, force=False, out=None, today=None, open_cooler=None, say=print) -> int:
    base = root()
    config = load_json(base/'studio-daily.json', {})
    state = load_json(base/'studio-daily-state.json', {})
    projects = load_json(base/'projects.json', None)
    if not isinstance(projects, list) or not projects or len(projects) > 20 or \
            any(not isinstance(p, dict) or not isinstance(p.get('site'), str) for p in projects):
        say('No projects to show. Add them to projects.json first.'); return 1
    values = {**load_json(base/'studio-draft.json', {}), 'preset': 'Projects'}

    try:
        summaries = fetch(config.get('command'), int(config.get('timeout', 120)))
        updated, kept = refresh(projects, summaries)
    except ValueError as e:
        updated, kept = [], [(p.get('name', p['site']), str(e)) for p in projects]
    say(f'Fresh numbers: {", ".join(updated) or "none"}')
    for name, why in kept:
        say(f'Kept earlier numbers for {name}: {why}')

    mark = fingerprint(projects, values)
    if mark == state.get('fingerprint') and not force and not dry_run:
        say('Nothing changed since the clip on the cooler was sent, so nothing was sent.')
        return 0 if updated else 1

    day = (today or date.today()).strftime('%Y%m%d')
    # A forced send of an unchanged picture needs a name the cooler does not hold yet.
    name = f'{PREFIX}{day}-{datetime.now():%H%M%S}.mkv' if force else f'{PREFIX}{day}-{mark[:6]}.mkv'
    with tempfile.TemporaryDirectory(prefix='rigdeck-daily-') as temp:
        try:
            clip = build(projects, values, Path(temp))
        except (ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
            say(f'Could not build the clip: {e}'); return 1
        if dry_run:
            folder = Path(out or base/'studio-daily-preview'); folder.mkdir(parents=True, exist_ok=True)
            for src, dst in [(clip, 'clip.mkv'), (Path(temp)/'preview.gif', 'preview.gif'), (Path(temp)/'poster.png', 'poster.png')]:
                shutil.copyfile(src, folder/dst)
            say(f'Dry run: built {folder}/clip.mkv. Nothing was sent to the cooler and nothing was saved.')
            return 0
        named = Path(temp)/name
        shutil.copyfile(clip, named)
        try:
            removed, free_kb = send(str(named), name, open_cooler)
        except Exception as e:  # the cooler, the converter or the cable: say so and keep everything as it was
            say(f'Could not send the clip to the cooler: {e}'); return 1
    if updated:
        save_json(base/'projects.json', projects)
    save_json(base/'studio-daily-state.json', {'fingerprint': mark, 'clip': name,
              'sentAt': datetime.now().astimezone().isoformat(timespec='seconds'),
              'updated': updated, 'kept': [k[0] for k in kept]})
    say(f'Sent {name}; it is now the only clip playing.' + (f' Removed {", ".join(removed)}.' if removed else '') +
        f' Free space on the cooler: {free_kb / 1024:.1f} MB.')
    return 0 if updated else 1
