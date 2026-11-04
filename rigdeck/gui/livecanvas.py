"""Sight glass: the round LCD as a window on the cooling loop.

The waterline is the measured request history, oldest minute on the left. The replay
raises it minute by minute; each request throws one droplet and the count climbs to
the real total. Nothing moves unless a measured request caused it, so a quiet site is
dead calm and an empty glass means no data, never zero.
"""
from datetime import datetime, timedelta
from functools import lru_cache
import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient)
from PySide6.QtSvg import QSvgRenderer

VOID = '#000000'    # LCD black disappears into the pump bezel
ICE = '#f2fbff'
MUTED = '#8fa6b4'
FAINT = '#c3d4de'
ALARM = '#ff5a4d'
FAMILY = 'Adwaita Sans'
LEFT, RIGHT = 14, 306   # oldest and newest minute; the chord is wider at the waterline
WATERLINE = 234         # calm surface
CREST = 96              # the portfolio's busiest minute stops here, so the logo stays dry
DRY = 86                # droplets never reach the logo
MIN_PEAK = 10           # a quiet portfolio must not draw a single request as a tidal wave
SWEEP = .7              # share of a site's turn spent replaying; the rest holds the result
SETTLE = .45            # seconds for the water to fall calm before the next site
RISE = .07              # sweep distance one minute takes to rise
MAX_DROPLETS = 24
GRAVITY = 430


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


def clock(moment):
    return moment.astimezone().strftime('%-I:%M %p').lower()


def mix(color, other, amount):
    a, b = QColor(color), QColor(other)
    return QColor(*(round(getattr(a, c)() + (getattr(b, c)() - getattr(a, c)())*amount)
                    for c in ('red', 'green', 'blue')))


def font(size, weight=QFont.DemiBold):
    result = QFont(FAMILY)
    result.setPixelSize(size)
    result.setWeight(weight)
    return result


def label(p, text, y, size, color, weight=QFont.DemiBold):
    p.setFont(font(size, weight))
    p.setPen(QColor(color))
    p.drawText(QRectF(0, y, 320, size + 8), Qt.AlignCenter, text)


@lru_cache(maxsize=64)
def _logo(path, stamp, width, height, tint):
    if path.lower().endswith('.svg'):
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return QImage()
        size = renderer.defaultSize()
        size.scale(width, height, Qt.KeepAspectRatio)
        image = QImage(size, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        p = QPainter(image)
        renderer.render(p)
        p.end()
    else:
        source = QImage(path)
        if source.isNull():
            return source
        image = source.convertToFormat(QImage.Format_ARGB32_Premultiplied).scaled(
            width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if tint and QColor(tint).isValid():
        p = QPainter(image)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(image.rect(), QColor(tint))
        p.end()
    return image


def load_logo(path, width, height, tint=''):
    """Fit a logo to a box, optionally recoloured. A dark one-colour mark needs a tint on
    a dark screen; keeping its alpha means no plate behind it."""
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        return QImage()
    return _logo(path, stamp, width, height, tint or '')


@lru_cache(maxsize=256)
def _hero(text):
    size = 116
    while True:
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)  # variable fonts overlap their own contours
        path.addText(0, 0, font(size, QFont.Black), text)
        box = path.boundingRect()
        if box.width() <= 232 or size <= 40:
            break
        size -= 4
    path.translate(160 - box.center().x(), 132 - box.center().y())
    return path


def _surface(heights):
    """Smooth curve through the minutes. It never dips below calm: troughs would be invented."""
    last = len(heights) - 1
    points = [QPointF(LEFT - 44, WATERLINE)]
    points += [QPointF(LEFT + (RIGHT-LEFT)*i/max(1, last), WATERLINE - h) for i, h in enumerate(heights)]
    points += [QPointF(RIGHT + 44, WATERLINE)]
    path = QPainterPath(points[0])
    for i in range(len(points) - 1):
        before, a, b, after = points[max(i-1, 0)], points[i], points[i+1], points[min(i+2, len(points)-1)]
        one = a + (b - before)/6
        two = b - (after - a)/6
        one.setY(min(one.y(), WATERLINE)); two.setY(min(two.y(), WATERLINE))
        path.cubicTo(one, two, b)
    return path


def _noise(seed):
    return abs(math.sin(seed*12.9898)*43758.5453) % 1


def _droplets(p, heights, values, sweep, seconds, color):
    """One droplet per measured request in a minute, thrown as the replay reaches it."""
    p.setPen(Qt.NoPen)
    for i, value in enumerate(values):
        age = (sweep - (i + .5)/len(values))*seconds
        if not value or not 0 <= age < 1.1:
            continue
        x = LEFT + (RIGHT-LEFT)*i/max(1, len(values)-1)
        for k in range(min(int(value), MAX_DROPLETS)):
            seed = i*97 + k*13 + 1
            launch = 80 + 120*_noise(seed + .3)
            y = WATERLINE - heights[i] - launch*age + GRAVITY*age*age/2
            if not DRY < y < WATERLINE:
                continue
            fade = min(1, (1.1 - age)/.3)
            dot = QColor(color); dot.setAlphaF(fade)
            p.setBrush(dot)
            p.drawEllipse(QPointF(x + (_noise(seed) - .5)*130*age, y),
                          2.2 + 1.6*_noise(seed + .7), 2.2 + 1.6*_noise(seed + .7))


def draw(project, report, record, elapsed, duration, freshness, still=False):
    image = QImage(320, 320, QImage.Format_RGB888)
    image.fill(QColor(VOID))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    try:
        history = minute_history(report, record)
        values = [v for _, v in history]
        unavailable = bool(record.get('error')) or not history
        stale = freshness.lower().startswith('stale')
        accent = QColor(MUTED if stale else project.get('color', '#89dcff'))
        replay = not (still or stale or unavailable) and any(values)
        # Logarithmic, so a burst on one site does not flatten a lone request on another.
        # The scale is shared, so sites still compare with each other.
        peak = max(max((v for r in report.get('sites', []) for _, v in minute_history(report, r)), default=0), MIN_PEAK)
        heights = [(WATERLINE - CREST)*math.log1p(v)/math.log1p(peak) for v in values]
        seconds = duration*SWEEP
        sweep = min(1, elapsed/seconds) if replay else 1
        if replay:
            settle = min(1, (duration - elapsed)/SETTLE)
            def risen(i):
                t = max(0, min(1, (sweep - (i + .5)/len(values))/RISE))
                t -= 1  # ease out with a small overshoot, as water does
                return 1 + 2.2*t*t*t + 1.2*t*t
            heights = [h*max(0, risen(i))*settle for i, h in enumerate(heights)]
        if not unavailable:
            glow = QRadialGradient(160, WATERLINE, 190)
            air = QColor(accent); air.setAlpha(46)
            fade = QColor(accent); fade.setAlpha(0)
            glow.setColorAt(0, air); glow.setColorAt(1, fade)
            p.fillRect(0, 0, 320, 320, glow)
        logo = load_logo(project.get('logo', ''), 148, 56, project.get('logoTint', ''))
        if logo.isNull():  # never leave a site unnamed
            label(p, project.get('name', project['site']), 40, 22, ICE, QFont.Bold)
        else:
            p.drawImage(QPointF(160 - logo.width()/2, 53 - logo.height()/2), logo)
        if unavailable:
            label(p, 'No data', 112, 54, MUTED, QFont.Black)
            label(p, freshness, 262, 13, FAINT)
            return image
        total = record.get('requests', 0)
        if sweep < 1:
            total = min(total, sum(v for i, v in enumerate(values) if (i + .5)/len(values) <= sweep))
        hero = _hero(f'{int(total):,}')
        caption = 'requests in 15 min' if any(values) else 'no requests in 15 min'
        p.setPen(Qt.NoPen); p.setBrush(QColor(ICE)); p.drawPath(hero)
        label(p, caption, 182, 15, ICE)
        # The water covers the type, then the same type returns in the dark where it is
        # submerged, so the numeral flips colour exactly at the waterline.
        surface = _surface(heights)
        water = QPainterPath(surface)
        water.lineTo(370, 340); water.lineTo(-50, 340); water.closeSubpath()
        fill = QLinearGradient(0, CREST, 0, 320)
        at = lambda y: (y - CREST)/(320 - CREST)
        fill.setColorAt(0, mix(accent, ICE, .12))
        fill.setColorAt(at(WATERLINE - 2), mix(accent, VOID, .12))
        fill.setColorAt(at(WATERLINE + 16), mix(accent, VOID, .72))
        fill.setColorAt(1, mix(accent, VOID, .94))
        p.setPen(Qt.NoPen); p.setBrush(fill); p.drawPath(water)
        p.save()
        p.setClipPath(water)
        ink = mix(accent, VOID, .92)
        p.setPen(Qt.NoPen); p.setBrush(ink); p.drawPath(hero)
        label(p, caption, 182, 15, ink)
        p.restore()
        hot = mix(accent, ICE, .6)
        p.setBrush(Qt.NoBrush)
        for width, alpha in ((13, 26), (7, 60)):
            halo = QColor(accent); halo.setAlpha(alpha)
            p.setPen(QPen(halo, width, Qt.SolidLine, Qt.RoundCap)); p.drawPath(surface)
        p.setPen(QPen(hot, 3, Qt.SolidLine, Qt.RoundCap)); p.drawPath(surface)
        if replay and sweep < 1:
            head = LEFT + (RIGHT-LEFT)*sweep
            glint = QLinearGradient(head - 44, 0, head + 3, 0)
            clear = QColor(ICE); clear.setAlpha(0)
            glint.setColorAt(0, clear); glint.setColorAt(.9, QColor(ICE)); glint.setColorAt(1, clear)
            p.setPen(QPen(QBrush(glint), 4, Qt.SolidLine, Qt.RoundCap)); p.drawPath(surface)
        if replay:
            _droplets(p, heights, values, elapsed/seconds, seconds, hot)
        cache = record.get('cachePct')
        errors = record.get('serverErrors', 0)
        size = record.get('bytes', 0)
        amount = f'{size/1024/1024:.1f} MB' if size >= 1024*1024 else f'{size/1024:.0f} KB'
        cached = 'Nothing to cache' if cache is None else f'{cache:.0f}% cached'
        p.setFont(font(13))
        metrics = p.fontMetrics()
        parts = [(cached, ICE), (amount, ICE), (f'{errors:,} error' + ('' if errors == 1 else 's'), ALARM if errors else ICE)]
        gap = 18
        x = 160 - (sum(metrics.horizontalAdvance(t) for t, _ in parts) + gap*2)/2
        for text, color in parts:
            p.setPen(QColor(color))
            p.drawText(QPointF(x, 264), text)
            x += metrics.horizontalAdvance(text) + gap
        footer = freshness
        if replay and sweep < 1:
            at_minute, count = history[min(len(history)-1, int(sweep*len(history)))]
            footer = f'Replay {clock(at_minute)}' + (f', +{count:g}' if count else '')
        label(p, footer, 272, 13, ALARM if stale else FAINT)
    finally:
        p.end()
    return image
