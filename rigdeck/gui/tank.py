"""The tank clip: a site's Google Search numbers surfacing, one by one, from a porthole of
glowing coolant, with the site's logo turning above. Built for the round 320 px cooler screen.

Blender renders each number's 7 s segment (tank_scene.py); this module decides which numbers
to show, keeps rendered segments in a cache so only a changed number is rendered again, adds
the labels and the round mask, and joins the segments into one clip in the cooler's format.
Rendering never opens or writes a USB device.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

DESIGN = 1            # bump when tank_scene.py changes the picture, so cached segments are rendered again
FRAMES, FPS = 175, 25  # one segment: 7 s, every motion a whole number of cycles
HERE = Path(__file__).parent
SCENE = HERE / 'tank_scene.py'
FONT = HERE / 'fonts' / 'AdwaitaSans-Black.ttf'
LABEL = SUB = '#ffffff'
SCRIM = (0.105, 0.004, 0.012)  # a darker depth of the liquid behind the labels, so small text keeps 4.5:1


def cache_dir() -> Path:
    return Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'rigdeck' / 'tank'


def when(end_date: str) -> str:
    d = date.fromisoformat(end_date)
    return f'28 days to {d.strftime("%b")} {d.day}'


def segments(summary: dict, positions: dict | None = None) -> list[dict]:
    """The numbers worth a turn on the screen, from a 28-day summary and, when given, the
    position bands. Each is one segment: the figure, how to write it, and two short labels."""
    current, deltas, period = summary['current'], summary.get('deltas') or {}, when(summary['range']['endDate'])
    out = [dict(key='shown', value=int(current['impressions']), prefix='', decimals=0, label='times shown on Google', sub=period)]
    if 'impressions' in deltas:
        change = int(deltas['impressions'])
        label = 'more than the 28 days before' if change > 0 else 'fewer than the 28 days before' if change < 0 else 'same as the 28 days before'
        out.append(dict(key='change', value=abs(change), prefix='+' if change > 0 else '-' if change < 0 else '', decimals=0, label=label, sub='times shown on Google'))
    out.append(dict(key='clicks', value=int(current['clicks']), prefix='', decimals=0, label='clicks from Google', sub=period))
    if positions and isinstance(positions.get('bands'), list):
        by = {b['band']: int(b['searches']) for b in positions['bands']}
        out.append(dict(key='searches', value=int(positions.get('searches', sum(by.values()))), prefix='', decimals=0, label='searches you showed up for', sub=period))
        out.append(dict(key='page-one', value=by.get('1-3', 0) + by.get('4-10', 0), prefix='', decimals=0, label='searches on page one', sub=period))
        out.append(dict(key='top-three', value=by.get('1-3', 0), prefix='', decimals=0, label='searches in the top three', sub=period))
    return out


def file_mark(path: str | Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return 'none'


def render_key(segment: dict, color: str, logo_png: str | Path, res: int, samples: int) -> str:
    """Changes exactly when the rendered pictures would."""
    scene = dict(design=DESIGN, value=segment['value'], prefix=segment['prefix'], decimals=segment['decimals'],
                 color=color.lower(), logo=file_mark(logo_png), res=res, samples=samples)
    return hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest()[:16]


def prepare_logo(path: str, tint: str, folder: Path) -> Path:
    """The logo as a clean RGBA picture the scene can hang in the tank (tint applied, as in the app)."""
    from .livecanvas import load_logo
    image = load_logo(path, 900, 372, tint)
    if image.isNull():
        raise ValueError('The logo could not be read. Choose a readable PNG, WebP, JPEG or SVG logo.')
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f'logo-{file_mark(path)}-{hashlib.sha256(tint.encode()).hexdigest()[:6]}.png'
    if not out.exists():
        image.save(str(out))
    return out


def render_segment(segment: dict, color: str, logo_png: Path, res=384, samples=72, blender=None, say=None, run=subprocess.run) -> Path:
    """Frames for one segment, from the cache when that exact picture was rendered before."""
    folder = cache_dir() / render_key(segment, color, logo_png, res, samples)
    if len(list(folder.glob('f*.png'))) == FRAMES:
        return folder
    exe = blender or os.environ.get('RIGDECK_BLENDER') or shutil.which('blender')
    if not exe:
        raise ValueError('Blender is not installed. The tank clip needs it to render (pacman -S blender).')
    shutil.rmtree(folder, ignore_errors=True); folder.mkdir(parents=True)
    if say:
        say(f'Rendering {segment["prefix"]}{segment["value"]:,} {segment["label"]}…')
    args = [exe, '-b', '--python', str(SCENE), '--', f'color={color}', f'value={segment["value"]}', f'prefix={segment["prefix"]}',
            f'decimals={segment["decimals"]}', f'logo={logo_png}', f'out={folder}', f'res={res}', f'samples={samples}',
            f'frames=0-{FRAMES - 1}', f'total={FRAMES}', f'font={FONT}']
    r = run(args, capture_output=True, text=True, timeout=3600)
    if r.returncode or len(list(folder.glob('f*.png'))) != FRAMES:
        shutil.rmtree(folder, ignore_errors=True)
        tail = (r.stderr or r.stdout or '').strip().splitlines()[-3:]
        raise ValueError('Blender did not finish the segment: ' + (' / '.join(tail) or f'exit {r.returncode}'))
    return folder


def _blur(a, r):
    import numpy as np
    for axis in (0, 1):
        c = np.cumsum(np.pad(a, [(r + 1, r) if i == axis else (0, 0) for i in range(3)], mode='edge'), axis=axis, dtype=np.float32)
        a = (np.take(c, range(2 * r + 1, c.shape[axis]), axis=axis) - np.take(c, range(0, c.shape[axis] - 2 * r - 1), axis=axis)) / (2 * r + 1)
    return a


def finish(frame: str | Path, label: str, sub: str, t: float, size=320):
    """One screen frame: soft bloom, the dark depth behind the labels, the labels themselves
    (fading in after the number settles and out before it dives), and the round mask."""
    import numpy as np
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath
    img = QImage(str(frame)).convertToFormat(QImage.Format_RGB888).scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(size, img.bytesPerLine())[:, :size * 3].reshape(size, size, 3).astype(np.float32) / 255
    bright = np.clip(a - .7, 0, 1) * 2.0
    a = np.clip(a + _blur(_blur(bright, 4), 4) * .30 + _blur(_blur(bright, 13), 13) * .28, 0, 1)
    show = max(0.0, min(1.0, (t - .26) / .10, (.90 - t) / .06))
    if (label or sub) and show > 0:
        ys = np.arange(size, dtype=np.float32)[:, None]; xs = np.arange(size, dtype=np.float32)[None, :]
        band = np.clip((ys - 216) / 12, 0, 1) * np.clip((286 - ys) / 12, 0, 1) * np.clip((xs - 24) / 22, 0, 1) * np.clip((296 - xs) / 22, 0, 1)
        m = (.86 * show * band)[..., None]
        a = a * (1 - m) + np.array(SCRIM, dtype=np.float32) * m
    out = QImage((a * 255).astype(np.uint8).tobytes(), size, size, size * 3, QImage.Format_RGB888).copy()
    p = QPainter(out); p.setRenderHint(QPainter.Antialiasing)
    square = QPainterPath(); square.addRect(0, 0, size, size)
    disc = QPainterPath(); disc.addEllipse(QPointF(size / 2, size / 2), size / 2 - .5, size / 2 - .5)
    p.fillPath(square.subtracted(disc), QColor(0, 0, 0))
    drift = 3.0 * __import__('math').sin(2 * 3.14159265 * t)
    def text(s, y, px, weight, color, spacing):
        f = QFont('Adwaita Sans'); f.setPixelSize(px); f.setWeight(QFont.Weight(weight)); f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        p.setFont(f); p.setOpacity(show * .5); p.setPen(QColor(0, 0, 0))
        p.drawText(QRectF(drift, y + 1 + (1 - show) * 6, size, px + 6), Qt.AlignHCenter | Qt.AlignVCenter, s)
        p.setOpacity(show); p.setPen(QColor(color))
        p.drawText(QRectF(drift, y + (1 - show) * 6, size, px + 6), Qt.AlignHCenter | Qt.AlignVCenter, s)
    if show > 0:
        if label: text(label, 232, 15, 700, LABEL, .2)
        if sub: text(sub, 253, 11, 600, SUB, .3)
    p.end()
    return out


def _ffmpeg(*args):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args], capture_output=True, timeout=600)
    if r.returncode:
        raise ValueError('Media conversion failed: ' + r.stderr.decode(errors='replace')[-400:])


def assemble(segs: list[dict], frame_dirs: list[Path], folder: Path) -> str:
    """Finish every frame and join the segments into one clip in the cooler's format, plus the
    GIF reviewed before sending and a poster of the first number settled."""
    folder = Path(folder); frames = folder / 'frames'; frames.mkdir(parents=True, exist_ok=True)
    n = 0
    for seg, source in zip(segs, frame_dirs):
        files = sorted(source.glob('f*.png'))
        for i, f in enumerate(files):
            finish(f, seg['label'], seg['sub'], i / len(files)).save(str(frames / f'out-{n:04}.png')); n += 1
    output = folder / 'tank.mkv'
    _ffmpeg('-framerate', str(FPS), '-i', str(frames / 'out-%04d.png'), '-an', '-c:v', 'libx264', '-profile:v', 'main', '-level:v', '3.1',
            '-pix_fmt', 'yuv420p', '-bf', '0', '-b:v', '1000k', str(output))
    _ffmpeg('-i', str(output), '-vf', 'fps=10,split[a][b];[a]palettegen[p];[b][p]paletteuse', str(folder / 'preview.gif'))
    shutil.copyfile(frames / f'out-{min(100, n - 1):04}.png', folder / 'poster.png')
    shutil.rmtree(frames, ignore_errors=True)
    return str(output)


def build(summary: dict, positions: dict | None, project: dict, folder: Path, res=384, samples=72, say=None, blender=None, run=subprocess.run) -> str:
    """The whole clip for one project: decide the numbers, render what changed, finish and join."""
    from PySide6.QtGui import QGuiApplication
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    QGuiApplication.instance() or QGuiApplication([])
    segs = segments(summary, positions)
    color = project.get('color') or '#89dcff'
    logo = project.get('logo')
    if not logo:
        raise ValueError(f'{project.get("name", project.get("site"))} has no logo set; the tank clip hangs the logo in the tank.')
    logo_png = prepare_logo(logo, project.get('logoTint', ''), cache_dir())
    dirs = [render_segment(s, color, logo_png, res, samples, blender, say, run) for s in segs]
    prune(keep=dirs)
    return assemble(segs, dirs, Path(folder))


def prune(keep: list[Path], older_than_hours=48):
    """Drop cached segments that this build did not use and that have sat unused for two days;
    yesterday's numbers rarely come back, and each segment is tens of megabytes."""
    import time
    keep = {Path(k).resolve() for k in keep}
    for folder in cache_dir().glob('*'):
        if folder.is_dir() and folder.resolve() not in keep and time.time() - folder.stat().st_mtime > older_than_hours * 3600:
            shutil.rmtree(folder, ignore_errors=True)
    for folder in keep:
        os.utime(folder, None)
