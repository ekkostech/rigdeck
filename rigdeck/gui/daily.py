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

With a "tank" section the clip is the tank design (tank.py) for one project, several of its
numbers in turn: {"tank": {"project": "macdigital.ca",
"positions": ["macdigital-search", "positions", "macdigital.ca"], "res": 384, "samples": 72}}.
Without it, the clip is the Projects design for every project.
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


def run_command(command, timeout=120, what='numbers') -> str:
    """Run a configured command and return what it printed, or say plainly why it could not."""
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise ValueError(f'Set the {what} command in studio-daily.json as a list, like ["macdigital-search", "all", "--json"].')
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ValueError(f'The {what} command was not found: {command[0]}')
    except subprocess.TimeoutExpired:
        raise ValueError(f'The {what} command took longer than {timeout} seconds.')
    if r.returncode:
        raise ValueError(f'The {what} command failed: ' + (r.stderr.strip() or f'exit {r.returncode}')[-300:])
    return r.stdout


def fetch(command, timeout=120) -> dict:
    """Run the numbers command; return {siteUrl: summary} for the sites it could read."""
    out = run_command(command, timeout)
    try:
        sites = json.loads(out)['sites']
        if not isinstance(sites, list): raise TypeError
    except (ValueError, KeyError, TypeError):
        raise ValueError('The numbers command did not print {"sites": [...]} as JSON.')
    return {s['siteUrl']: s for s in sites if isinstance(s, dict) and isinstance(s.get('siteUrl'), str)}


def fetch_positions(command, timeout=120) -> dict:
    """Run the positions command; return its JSON object (searches and bands)."""
    try:
        data = json.loads(run_command(command, timeout, 'positions'))
        if not isinstance(data, dict) or not isinstance(data.get('bands'), list): raise TypeError
    except (ValueError, TypeError):
        raise ValueError('The positions command did not print {"searches": N, "bands": [...]} as JSON.')
    return data


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
        c.upload_media(data, name)      # waits for quiet, holds the cooler alone while sending, confirms the file
        screen = add_to_carousel(c, name)
        screen.write(c, screen.files, [name])
        c.send(b'\xc0\x00\x00\x00')  # no stock text, logo or readouts over the clip
        c.save()
        removed = []
        for old in [f for f in screen.files if f.startswith(PREFIX) and f != name]:
            c.settle()                  # never two storage changes close together
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

    tank_cfg = config.get('tank') if isinstance(config.get('tank'), dict) else None
    if tank_cfg:
        # One site, several of its numbers, in the tank: see tank.py.
        from . import tank
        wanted = str(tank_cfg.get('project', ''))
        project = next((p for p in projects if wanted in (p.get('site'), p.get('name'))), None)
        if not project or not project.get('snapshot'):
            say(f'No project with numbers called {wanted!r} in projects.json; set "tank": {{"project": ...}} to one of them.'); return 1
        summary = project['snapshot']
        positions = None
        try:
            positions = fetch_positions(tank_cfg.get('positions'), int(config.get('timeout', 120)))
            if str(positions.get('range', {}).get('endDate', summary['range']['endDate'])) != summary['range']['endDate']:
                raise ValueError('their period does not match the summary')
        except ValueError as e:
            earlier = state.get('positions')
            if isinstance(earlier, dict) and earlier.get('range', {}).get('endDate') == summary['range']['endDate']:
                positions = earlier; say(f'Using the position numbers fetched earlier for this period: {e}')
            else:
                say(f'Leaving out the position numbers: {e}')
        res, samples = int(tank_cfg.get('res', 384)), int(tank_cfg.get('samples', 72))
        segs = tank.segments(summary, positions)
        mark = hashlib.sha256(json.dumps(['tank', tank.DESIGN, segs, project.get('color'), tank.file_mark(project.get('logo', '')), project.get('logoTint', ''), res, samples], sort_keys=True).encode()).hexdigest()
        def make(temp):
            return tank.build(summary, positions, project, Path(temp), res, samples, say=say)
        say('Numbers for the tank: ' + ', '.join(f'{s["prefix"]}{s["value"]:,} {s["label"]}' for s in segs))
    else:
        mark = fingerprint(projects, values)
        def make(temp):
            return build(projects, values, Path(temp))
        positions = None
    if mark == state.get('fingerprint') and not force and not dry_run:
        say('Nothing changed since the clip on the cooler was sent, so nothing was sent.')
        return 0 if updated else 1

    day = (today or date.today()).strftime('%Y%m%d')
    # A forced send of an unchanged picture needs a name the cooler does not hold yet.
    name = f'{PREFIX}{day}-{datetime.now():%H%M%S}.mkv' if force else f'{PREFIX}{day}-{mark[:6]}.mkv'
    with tempfile.TemporaryDirectory(prefix='rigdeck-daily-') as temp:
        try:
            clip = make(temp)
        except (ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
            say(f'Could not build the clip: {e}'); return 1
        if dry_run:
            folder = Path(out or base/'studio-daily-preview'); folder.mkdir(parents=True, exist_ok=True)
            for src, dst in [(clip, 'clip.mkv'), (Path(clip).parent/'preview.gif', 'preview.gif'), (Path(clip).parent/'poster.png', 'poster.png')]:
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
              'updated': updated, 'kept': [k[0] for k in kept], **({'positions': positions} if positions else {})})
    say(f'Sent {name}; it is now the only clip playing.' + (f' Removed {", ".join(removed)}.' if removed else '') +
        f' Free space on the cooler: {free_kb / 1024:.1f} MB.')
    return 0 if updated else 1
