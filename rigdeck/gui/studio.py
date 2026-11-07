"""Local screen composition. Rendering never opens or writes a USB device."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

from PySide6.QtCore import Property, QObject, QPointF, QRectF, Qt, QUrl, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from .bridge import run_async
from .livecanvas import clock, draw, load_logo

ROOT = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'rigdeck'
STALE_AFTER = 180  # seconds; older Cloudflare numbers are shown as stale and never built into a clip
DEFAULT = dict(text='YOUR SIGNATURE', subtitle='AORUS · WATERFORCE', font='Adwaita Sans',
               size=26, color='#89dcff', background='#090f17', effect='Orbit', y=170,
               media='', logo='', preset='Signature', duration=6)


def validate(values):
    d = {**DEFAULT, **values}
    for key in ('text', 'subtitle', 'font', 'media', 'logo', 'preset', 'effect'):
        if not isinstance(d[key], str):
            raise ValueError(f'{key} must be text')
    if len(d['text']) > 64 or len(d['subtitle']) > 80:
        raise ValueError('Use up to 64 characters in the title and 80 in the subtitle.')
    for key in ('color', 'background'):
        if not QColor(d[key]).isValid():
            raise ValueError(f'Choose a valid {key} colour, such as #89dcff.')
    for key, low, high in [('size', 12, 48), ('y', 60, 240), ('duration', 3, 12)]:
        d[key] = int(d[key])
        if not low <= d[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
    if d['effect'] not in ('Orbit', 'Pulse', 'Still') or d['preset'] not in ('Signature', 'Traffic', 'Projects', 'Live projects', 'Tank'):
        raise ValueError('Unknown design preset or animation.')
    for key in ('media', 'logo'):
        if d[key] and not Path(d[key]).is_file():
            raise ValueError(f'The {key} file is missing. Choose it again or clear it.')
    return d


def check_stats(s):
    """Refuse anything that is not a usable 28-day Search Console snapshot."""
    if not isinstance(s, dict): raise ValueError('Snapshot must be a JSON object.')
    if not isinstance(s.get('siteUrl'),str) or not s['siteUrl'].startswith(('sc-domain:', 'https://')): raise ValueError('Choose a Search Console snapshot with a site URL.')
    for k in ('clicks','impressions','ctr'):
        if isinstance(s['current'][k], bool) or not isinstance(s['current'][k], (int,float)) or not math.isfinite(s['current'][k]) or s['current'][k] < 0:
            raise ValueError('Snapshot contains invalid metrics.')
    from datetime import date
    date.fromisoformat(s['range']['endDate']); date.fromisoformat(s['range']['startDate'])
    if s['range']['days'] != 28: raise ValueError('Use a 28-day snapshot.')
    if len(s.get('dailyRows',[])) > 31: raise ValueError('Too many daily rows.')
    for r in s.get('dailyRows',[]):
        if not isinstance(r['impressions'], (int,float)) or not math.isfinite(r['impressions']) or r['impressions'] < 0:
            raise ValueError('Invalid daily impressions.')
    return s


def line(p, text, y, size, color, font='Adwaita Sans', bold=False):
    f = QFont(font); f.setPixelSize(size); f.setBold(bold)
    p.setFont(f); p.setPen(QColor(color))
    # Keep long titles inside the circular display, rather than silently cropping them.
    while p.fontMetrics().horizontalAdvance(text) > 250 and f.pixelSize() > 10:
        f.setPixelSize(f.pixelSize() - 1); p.setFont(f)
    p.drawText(QRectF(35, y, 250, size + 12), Qt.AlignHCenter | Qt.AlignVCenter, text)


def compose(d, t=0, background=None, stats=None):
    image = QImage(320, 320, QImage.Format_RGB888)
    image.fill(QColor(d['background']))
    p = QPainter(image); p.setRenderHint(QPainter.Antialiasing)
    if background and not background.isNull():
        p.drawImage(QRectF(0, 0, 320, 320), background)
        p.fillRect(0, 0, 320, 320, QColor(0, 0, 0, 95))
    accent = QColor(d['color'])
    glow = QRadialGradient(160, 118, 180)
    c = QColor(accent); c.setAlpha(45); glow.setColorAt(0, c); glow.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(0, 0, 320, 320, glow)
    phase = 0 if d['effect'] == 'Still' else t / d['duration'] * 2 * math.pi
    # Concentric bevels and moving specular arcs give the small LCD physical depth.
    p.setBrush(Qt.NoBrush)
    for radius, color, width in [(151, '#203444', 5), (148, '#080f17', 3), (144, '#3a6075', 1), (132, '#1b3445', 1)]:
        p.setPen(QPen(QColor(color), width)); p.drawEllipse(QRectF(160-radius, 160-radius, radius*2, radius*2))
    p.setPen(QPen(accent, 3))
    angle = int(phase * 180 / math.pi * 16)
    p.drawArc(QRectF(13, 13, 294, 294), angle, 75*16)
    p.drawArc(QRectF(13, 13, 294, 294), angle+180*16, 28*16)
    for i in range(60):
        a = i * math.pi / 30
        r = 138; length = 5 if i % 5 == 0 else 2
        p.setPen(QPen(accent if i % 5 == 0 else QColor('#38566a'), 1))
        p.drawLine(int(160+math.sin(a)*r), int(160+math.cos(a)*r),
                   int(160+math.sin(a)*(r-length)), int(160+math.cos(a)*(r-length)))
    if d['logo']:
        p.save()
        p.translate(160, 90)
        tint = d.get('logoTint', '')
        if d['logo'].lower().endswith('.svg') and not tint:
            logo = QSvgRenderer(d['logo'])
            if not logo.isValid():
                p.end(); raise ValueError('The logo SVG could not be read.')
            # Offset silhouettes form a shallow extrusion; the source mark remains intact.
            for depth in range(5, 0, -1):
                p.setOpacity(.12); logo.render(p, QRectF(-38+depth, -34+depth, 76, 67))
            p.setOpacity(1); logo.render(p, QRectF(-38, -34, 76, 67))
        else:
            logo = load_logo(d['logo'], 150, 65, tint)
            if logo.isNull():
                p.end(); raise ValueError('Choose a readable PNG, WebP, JPEG or SVG logo.')
            p.drawImage(QPointF(-logo.width()/2, -logo.height()/2), logo)
        p.restore()
    else:
        line(p, 'SCREEN STUDIO', 72, 12, '#a0b4c8')
    if d['preset'] == 'Traffic':
        line(p, stats.get('displayName', stats.get('siteUrl', 'MACDIGITAL.CA').removeprefix('sc-domain:')).upper() if stats else 'MACDIGITAL.CA', 124, 16, '#edf5fc', bold=True)
        if stats and stats.get('liveMetrics'):
            live=stats['liveMetrics']; index=int(t / (d['duration']/3)) % 3
            metrics=[('REQUESTS · LAST 15 MIN', str(live.get('requests', '—'))),
                     ('CACHE HIT RATE', ('%.1f%%' % live['cachePct']) if live.get('cachePct') is not None else '—'),
                     ('SERVER ERRORS · 15 MIN', str(live.get('serverErrors','—')))]
            label,value=metrics[index]
            if live.get('error'): label,value='DATA UNAVAILABLE','—'
            line(p,value,151,38,d['color'],bold=True)
            line(p,label,196,10,'#edf5fc')
            line(p,'%.1f KB transferred' % (live.get('bytes',0)/1024) if not live.get('error') else 'Check connection in Rigdeck',220,11,'#a0b4c8')
            line(p,stats.get('freshness','Fetching…'),250,10,'#a0b4c8')
        elif stats:
            current = stats['current']; index = int(t / (d['duration']/3)) % 3
            metrics = [('SEARCH CLICKS', f"{current['clicks']:,}"),
                       ('IMPRESSIONS', f"{current['impressions']:,}"),
                       ('SEARCH CTR', f"{current['ctr']:.2f}%")]
            label, value = metrics[index]
            line(p, value, 151, 38, d['color'], bold=True)
            line(p, label, 196, 11, '#edf5fc')
            rows = stats.get('dailyRows', [])
            vals = [r['impressions'] for r in rows]
            maximum = max(vals, default=1) or 1
            p.setPen(QPen(accent, 2))
            for i in range(1, len(vals)):
                p.drawLine(int(65+(i-1)*190/max(1,len(vals)-1)), int(244-vals[i-1]/maximum*22),
                           int(65+i*190/max(1,len(vals)-1)), int(244-vals[i]/maximum*22))
            line(p, '28D · '+stats['range']['endDate'], 250, 10, '#a0b4c8')
        else:
            line(p, 'CONNECT DATA', 171, 23, d['color'], bold=True)
            line(p, 'Search Console snapshot', 214, 12, '#a0b4c8')
    else:
        if d['effect'] == 'Pulse': p.setOpacity(.75 + .25*math.cos(phase))
        line(p, d['text'], d['y'], d['size'], d['color'], d['font'], True)
        p.setOpacity(1)
        line(p, d['subtitle'], d['y']+d['size']+9, 12, '#edf5fc', d['font'])
    p.end()
    return image


def command(args):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args],
                       capture_output=True, timeout=90)
    if r.returncode:
        raise ValueError('Media conversion failed: '+r.stderr.decode(errors='replace')[-400:])


def encode(frames, folder, gif_fps=15):
    """Encode numbered frames to the device format, plus the GIF reviewed before sending."""
    output = folder/('studio-'+uuid.uuid4().hex[:8]+'.mkv')
    command(['-framerate','25','-i',str(frames/'out-%04d.png'),'-an','-c:v','libx264',
             '-profile:v','main','-level:v','3.1','-pix_fmt','yuv420p','-bf','0','-b:v','1000k',str(output)])
    command(['-i',str(output),'-vf',f'fps={gif_fps},split[a][b];[a]palettegen[p];[b][p]paletteuse',str(folder/'preview.gif')])
    return output


def render(values, folder, stats=None):
    d = validate(values); folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rigdeck-frames-') as temp:
        frames = Path(temp)
        if d['media']:
            command(['-stream_loop','-1','-i',d['media'],'-t',str(d['duration']),
                     '-vf',"crop=min(iw\\,ih):min(iw\\,ih),scale=320:320,fps=25",str(frames/'bg-%04d.png')])
        backgrounds = sorted(frames.glob('bg-*.png'))
        for i in range(d['duration']*25):
            bg = QImage(str(backgrounds[i % len(backgrounds)])) if backgrounds else None
            frame = compose(d, i/25, bg, stats)
            frame.save(str(frames/f'out-{i:04}.png'))
        output = encode(frames, folder)
        # First frame for reduced-motion preview.
        compose(d, 0, QImage(str(backgrounds[0])) if backgrounds else None, stats).save(str(folder/'poster.png'))
    return str(output)


class ScreenStudio(QObject):
    changed = Signal()
    def __init__(self):
        super().__init__()
        self._draft = DEFAULT.copy(); self._busy=False; self._error=''; self._output=''; self._preview=''; self._poster=''; self._note=''
        self._temp = tempfile.TemporaryDirectory(prefix='rigdeck-studio-')
        try: self._draft = validate(json.loads((ROOT/'studio-draft.json').read_text()))
        except (OSError, ValueError, TypeError): pass
        self._projects=[]; self._live_data={}; self._live_error=''; self._refreshing=False
        try:
            projects=json.loads((ROOT/'projects.json').read_text())
            if not isinstance(projects,list) or len(projects)>20: raise ValueError('Invalid projects')
            if any(not isinstance(p,dict) or not isinstance(p.get('site'),str) for p in projects): raise ValueError('Invalid project')
            self._projects=projects
        except (OSError,ValueError): pass
        self._live_timer=QTimer(self, interval=60000, timeout=self.refreshLive)
        self._live_timer.start()
        QTimer.singleShot(100,self.refreshLive)
        self._stats = None
        try:
            self._stats = self.read_stats(ROOT/'traffic-snapshot.json')
        except (OSError, ValueError, KeyError, TypeError): pass
    @staticmethod
    def read_stats(path):
        if Path(path).stat().st_size > 1_000_000: raise ValueError('Snapshot must be smaller than 1 MB.')
        return check_stats(json.loads(Path(path).read_text()))
    projects = Property('QVariantList', lambda s:s._projects, constant=True)
    liveStatus = Property(str, lambda s:'Refreshing Cloudflare…' if s._refreshing else s._live_error or ('Cloudflare · rolling 15 minutes · refreshes every minute · includes bots' if s._live_data else 'Connecting to Cloudflare…'), notify=changed)
    @Slot()
    def refreshLive(self):
        if self._refreshing or not self._projects: return
        from .cloudflare import fetch
        self._refreshing=True; self.changed.emit()
        def done(data):
            self._live_data=data; self._live_error=''; self._refreshing=False; self.changed.emit()
        def failed(e):
            self._live_error=str(e); self._refreshing=False; self.changed.emit()
        run_async(lambda:fetch([p['site'] for p in self._projects]),done,failed)
    def live_frame(self, elapsed, still=False):
        if not self._projects: return compose({**DEFAULT,'text':'NO PROJECTS'})
        index=int(elapsed/self._draft['duration'])%len(self._projects); project=self._projects[index]
        record=next((r for r in self._live_data.get('sites',[]) if r['site']==project['site']),{'error':'Waiting for data'})
        stamp=self._live_data.get('fetchedAt')
        age=int((datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()) if stamp else None
        freshness=f'Stale, {age}s old' if age is not None and age>STALE_AFTER else f'Updated {age}s ago' if age is not None else 'Waiting for data'
        return draw(project, self._live_data, record, elapsed % self._draft['duration'],
                    self._draft['duration'], freshness, still or self._draft['effect']=='Still')

    draft = Property('QVariantMap', lambda s:s._draft, notify=changed)
    busy = Property(bool, lambda s:s._busy, notify=changed)
    note = Property(str, lambda s:s._note, notify=changed)  # what a long build is doing right now
    error = Property(str, lambda s:s._error, notify=changed)
    ready = Property(bool, lambda s:bool(s._output), notify=changed)
    preview = Property(str, lambda s:s._preview, notify=changed)
    poster = Property(str, lambda s:s._poster, notify=changed)
    output = Property(str, lambda s:QUrl.fromLocalFile(s._output).toString() if s._output else '', notify=changed)
    fonts = Property('QStringList', lambda s:QFontDatabase.families(), constant=True)
    trafficInfo = Property(str, lambda s: ('Google Search · '+s._stats['range']['startDate']+' to '+s._stats['range']['endDate']+' · imported snapshot, not live') if s._stats else 'No analytics snapshot connected', notify=changed)
    @Slot(str, 'QVariant')
    def edit(self, key, value):
        if self._busy or key not in DEFAULT: return
        self._draft[key]=value; self._output=''; self._error=''; self.changed.emit()
        try:
            ROOT.mkdir(parents=True, exist_ok=True)
            temp=ROOT/'studio-draft.json.tmp'; temp.write_text(json.dumps(self._draft)); temp.replace(ROOT/'studio-draft.json')
        except OSError as e:
            self._error=f'Draft could not be saved: {e}'; self.changed.emit()
    @Slot(str, str)
    def chooseFile(self, key, url):
        self.edit(key, QUrl(url).toLocalFile())
    @Slot(str)
    def importStats(self, url):
        if self._busy: return
        try:
            stats=self.read_stats(QUrl(url).toLocalFile())
            ROOT.mkdir(parents=True, exist_ok=True)
            temp=ROOT/'traffic-snapshot.json.tmp'; temp.write_text(json.dumps(stats)); temp.replace(ROOT/'traffic-snapshot.json')
            self._stats=stats; self._output=''; self._error=''
        except (OSError, ValueError, KeyError, TypeError) as e: self._error=f'Could not import snapshot: {e}'
        self.changed.emit()
    @Slot()
    def render(self):
        if self._busy: return
        try: d=validate(self._draft)
        except (ValueError, TypeError) as e:
            self._error=str(e); self.changed.emit(); return
        self._busy=True; self._error=''; self._output=''; self._note=''; self.changed.emit()
        folder=Path(self._temp.name)/uuid.uuid4().hex
        def done(path):
            self._output=path; self._preview=QUrl.fromLocalFile(str(folder/'preview.gif')).toString()
            self._poster=QUrl.fromLocalFile(str(folder/'poster.png')).toString()
            self._busy=False; self._note=''; self.changed.emit()
        def failed(e):
            self._busy=False; self._note=''; self._error=str(e); self.changed.emit()
        def note(text):
            from .bridge import on_main
            def show(): self._note=text; self.changed.emit()
            on_main(show)
        jobs={'Projects':lambda:render_projects(d,folder,self._projects),
              'Live projects':lambda:render_live(d,folder,self._projects,self._live_data),
              'Tank':lambda:render_tank(folder,self._projects,note)}
        run_async(jobs.get(d['preset'],lambda:render(d,folder,self._stats)),done,failed)
    @Slot()
    def clearPreview(self):
        """Leave a built snapshot and return to the live canvas."""
        if self._busy: return
        self._output=''; self._error=''; self.changed.emit()


def render_projects(values, folder, projects):
    """Build one continuous portfolio clip, preserving each site's own data and logo."""
    if not projects: raise ValueError('No projects configured.')
    if len(projects)>20: raise ValueError('Use at most 20 projects.')
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    clips=[]
    for i,project in enumerate(projects):
        d={**values,'preset':'Traffic','logo':project.get('logo',''),'color':project.get('color',values['color']),'logoTint':project.get('logoTint','')}
        stats={**project['snapshot'],'displayName':project.get('name',project['site'])}
        clips.append(render(d,folder/str(i),stats))
    listing=folder/'concat.txt'
    listing.write_text(''.join("file '"+str(Path(c).resolve()).replace("'", "'\\''")+"'\n" for c in clips))
    output=folder/('projects-'+uuid.uuid4().hex[:8]+'.mkv')
    command(['-f','concat','-safe','0','-i',str(listing),'-c','copy',str(output)])
    command(['-i',str(output),'-vf','fps=10,split[a][b];[a]palettegen[p];[b][p]paletteuse',str(folder/'preview.gif')])
    (folder/'poster.png').write_bytes((folder/'0'/'poster.png').read_bytes())
    return str(output)


def render_live(values, folder, projects, report):
    """One full rotation of the live canvas. The cooler only plays stored clips and its flash
    must not be rewritten on a timer, so this is a labelled snapshot built on request."""
    if not projects: raise ValueError('No projects configured.')
    if len(projects)>20: raise ValueError('Use at most 20 projects.')
    stamp=report.get('fetchedAt') if isinstance(report,dict) else None
    if not stamp: raise ValueError('Cloudflare numbers have not arrived yet. Choose Refresh Cloudflare now, then build again.')
    captured=datetime.fromisoformat(stamp)
    if (datetime.now(timezone.utc)-captured).total_seconds()>STALE_AFTER:
        raise ValueError('These Cloudflare numbers are over 3 minutes old. Choose Refresh Cloudflare now, then build again.')
    records=[next((r for r in report.get('sites',[]) if r['site']==p['site']),{'error':'Not in report'}) for p in projects]
    if all(r.get('error') for r in records):
        raise ValueError('Cloudflare returned no usable numbers. Choose Refresh Cloudflare now, then build again.')
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    frames_per_site=values['duration']*25
    freshness=f'As of {clock(captured)}'
    still=values['effect']=='Still'
    def frame(project,record,seconds):
        return draw(project,report,record,seconds,values['duration'],freshness,still)
    with tempfile.TemporaryDirectory(prefix='rigdeck-frames-') as temp:
        frames=Path(temp)
        for i,(project,record) in enumerate(zip(projects,records)):
            for n in range(frames_per_site):
                frame(project,record,n/25).save(str(frames/f'out-{i*frames_per_site+n:04}.png'))
        output=encode(frames,folder,gif_fps=10)
    # The result of the first site's replay, not the calm water it starts from.
    frame(projects[0],records[0],values['duration']*.85).save(str(folder/'poster.png'))
    return str(output)


def render_tank(folder, projects, note=None):
    """The tank for the project named in studio-daily.json (or the first project): its stored
    numbers, the position numbers when they can be fetched, rendered segments reused."""
    from . import daily, tank
    if not projects: raise ValueError('No projects configured.')
    config = daily.load_json(ROOT/'studio-daily.json', {})
    cfg = config.get('tank') if isinstance(config.get('tank'), dict) else {}
    wanted = str(cfg.get('project', ''))
    project = next((p for p in projects if wanted and wanted in (p.get('site'), p.get('name'))), None) or \
              next((p for p in projects if p.get('snapshot')), None)
    if not project or not project.get('snapshot'):
        raise ValueError('No project has Search Console numbers yet. Run rigdeck studio-daily, or import a snapshot.')
    summary = project['snapshot']
    positions = None
    if cfg.get('positions'):
        if note: note('Fetching position numbers…')
        try:
            positions = daily.fetch_positions(cfg['positions'], int(config.get('timeout', 120)))
            if str(positions.get('range', {}).get('endDate', summary['range']['endDate'])) != summary['range']['endDate']: positions = None
        except ValueError:
            positions = None
    if positions is None:
        earlier = daily.load_json(ROOT/'studio-daily-state.json', {}).get('positions')
        if isinstance(earlier, dict) and earlier.get('range', {}).get('endDate') == summary['range']['endDate']: positions = earlier
    return tank.build(summary, positions, project, Path(folder), int(cfg.get('res', 384)), int(cfg.get('samples', 72)), say=note)
