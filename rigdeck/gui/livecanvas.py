"""Measured minute history, replayed on the circular display. No invented events."""
from datetime import datetime, timedelta
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer

INK = '#09121b'
TRACK = '#263b4b'
FROST = '#d4f3ff'
MUTED = '#8da9b9'
CACHE = '#79dcc5'
ERROR = '#ff806f'


def minute_history(report, record):
    """Preserve partial edge minutes and fill missing buckets only in valid reports."""
    if record.get('error') or not report.get('start') or not report.get('end'):
        return []
    start = datetime.fromisoformat(report['start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(report['end'].replace('Z', '+00:00'))
    if not timedelta(0) < end - start <= timedelta(minutes=16):
        raise ValueError('Invalid analytics window')
    first = start.replace(second=0, microsecond=0)
    buckets = {}
    for row in record.get('series', []):
        at = datetime.fromisoformat(row['at'].replace('Z', '+00:00')).replace(second=0, microsecond=0)
        value = row['value']
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid request count')
        buckets[at] = buckets.get(at, 0) + value
    result = []
    while first < end:
        result.append((first, buckets.get(first, 0)))
        first += timedelta(minutes=1)
    return result


def point(radius, angle):
    a = math.radians(angle)
    return QPointF(160 + math.cos(a)*radius, 160 + math.sin(a)*radius)


def caption(p, text, y, size=11, color=FROST, family='Adwaita Sans', bold=False):
    font = QFont(family); font.setPixelSize(size); font.setBold(bold)
    p.setFont(font); p.setPen(QColor(color))
    while p.fontMetrics().horizontalAdvance(text) > 190 and font.pixelSize() > 8:
        font.setPixelSize(font.pixelSize()-1); p.setFont(font)
    p.drawText(QRectF(65, y, 190, size+7), Qt.AlignCenter, text)


def draw(project, report, record, elapsed, duration, freshness, still=False):
    image = QImage(320, 320, QImage.Format_RGB888); image.fill(QColor(INK))
    p = QPainter(image); p.setRenderHint(QPainter.Antialiasing)
    try:
        accent = QColor(project.get('color', '#89dcff'))
        history = minute_history(report, record)
        unavailable = bool(record.get('error')) or not history
        stale = freshness.startswith('STALE')
        # Same linear scale across all sites in this fetched report.
        scale = max((v for r in report.get('sites', []) for _, v in minute_history(report, r)), default=1) or 1
        p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(TRACK), 1))
        p.drawEllipse(QRectF(5, 5, 310, 310))
        selected = min(len(history)-1, int((elapsed % duration)/duration*len(history))) if history else -1
        replay = not (still or stale or unavailable) and any(v for _, v in history)
        if replay:
            scan_angle = 135 + (elapsed % duration)/duration*270
            beam = QColor(FROST); beam.setAlpha(60)
            p.setPen(QPen(beam, 1)); p.drawLine(point(112, scan_angle), point(150, scan_angle))
        for i, (_, value) in enumerate(history):
            angle = 135 + (i+.5)*270/len(history)
            color = QColor(MUTED) if stale else accent
            active = replay and i == selected
            if value:
                color.setAlpha(255 if active or not replay else 155)
                p.setPen(QPen(color, 7, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(point(123, angle), point(123+25*value/scale, angle))
            else:
                p.setPen(QPen(QColor(TRACK), 3, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(point(123, angle), point(125, angle))
            if active:
                p.setPen(Qt.NoPen); p.setBrush(QColor(FROST))
                p.drawEllipse(point(115, angle), 2.5, 2.5); p.setBrush(Qt.NoBrush)
        # Cache share is an absolute 0–100% arc, not another decorative orbit.
        p.setPen(QPen(QColor(TRACK), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(56, 56, 208, 208), 225*16, -270*16)
        cache = record.get('cachePct') if not unavailable else None
        if cache is not None:
            p.setPen(QPen(QColor(MUTED if stale else CACHE), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(56, 56, 208, 208), 225*16, -round(270*16*max(0,min(100,cache))/100))
        caption(p, 'NO DATA' if unavailable else f'SCALE {scale:g} / MIN', 42, 8, MUTED, 'Adwaita Mono')
        logo = project.get('logo', '')
        area = QRectF(112, 73, 96, 39)
        if project.get('logoPlate'):
            p.setPen(Qt.NoPen); p.setBrush(QColor('#eff7fc')); p.drawRoundedRect(area.adjusted(-5,-3,5,3),5,5)
        if logo.lower().endswith('.svg'):
            renderer = QSvgRenderer(logo)
            if renderer.isValid():
                size = renderer.defaultSize(); size.scale(96, 39, Qt.KeepAspectRatio)
                renderer.render(p, QRectF(160-size.width()/2, 92.5-size.height()/2, size.width(), size.height()))
        elif logo:
            logo_image = QImage(logo).scaled(96, 39, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawImage(QPointF(160-logo_image.width()/2, 92.5-logo_image.height()/2), logo_image)
        caption(p, project.get('name', project['site']).upper(), 115, 13, bold=True)
        caption(p, '—' if unavailable else f"{record['requests']:,}", 136, 39, FROST, 'Nimbus Sans Narrow', True)
        caption(p, 'REQUESTS / 15 MIN', 180, 10, MUTED, 'Adwaita Mono')
        cache_text = '—' if cache is None else f'{cache:.0f}%'
        errors = '—' if unavailable else str(record.get('serverErrors', 0))
        caption(p, f'{cache_text} CACHE   ·   {errors} 5XX', 205, 11,
                ERROR if not unavailable and record.get('serverErrors', 0) else CACHE, 'Adwaita Mono')
        size = record.get('bytes', 0)
        bandwidth = f'{size/1024/1024:.1f} MB' if size >= 1024*1024 else f'{size/1024:.1f} KB'
        caption(p, 'DATA UNAVAILABLE' if unavailable else bandwidth+' TRANSFERRED', 225, 10, MUTED, 'Adwaita Mono')
        if unavailable:
            replay_text = 'WAITING FOR CLOUDFLARE'
        elif not any(v for _, v in history):
            replay_text = 'NO REQUESTS IN WINDOW'
        elif stale or still:
            replay_text = '15-MIN HISTORY · PAUSED' if stale else '15-MIN REQUEST HISTORY'
        else:
            at, count = history[selected]
            replay_text = f"REPLAY {at.astimezone():%H:%M} · {count:g} REQ"
        caption(p, replay_text, 259, 10, FROST, 'Adwaita Mono')
        caption(p, freshness, 278, 9, ERROR if stale else MUTED, 'Adwaita Mono')
    finally:
        p.end()
    return image
