"""The tank clip: which numbers it shows, that only changed numbers are rendered again, that the
labels stay readable, and that the daily job can build and send it."""
import json
import os
import stat
import subprocess
import sys
from datetime import date
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip("PySide6")
pytest.importorskip("numpy")
from PySide6.QtGui import QGuiApplication, QImage
from rigdeck.gui import daily, tank
from tests.test_daily import FakeCooler, home, numbers, run, summary  # noqa: F401  (home is a fixture)


@pytest.fixture(scope='module', autouse=True)
def qt_app():
    yield QGuiApplication.instance() or QGuiApplication([])


SUMMARY = {**summary('macdigital.ca', 5, end='2026-11-03', start='2026-10-07'),
           'current': {'clicks': 5, 'impressions': 2603, 'ctr': 0.19, 'avgPosition': 53.8}, 'deltas': {'clicks': 1, 'impressions': 305}}
POSITIONS = {'range': {'startDate': '2026-10-07', 'endDate': '2026-11-03', 'days': 28}, 'searches': 180,
             'bands': [{'band': '1-3', 'searches': 8}, {'band': '4-10', 'searches': 9}, {'band': '11-20', 'searches': 15}, {'band': '21-50', 'searches': 39}, {'band': '51+', 'searches': 109}]}

FAKE_BLENDER = '''#!/usr/bin/env python3
"""Stands in for Blender: writes the frames a segment render would, and logs that it ran."""
import os, struct, sys, zlib
args = dict(a.split('=', 1) for a in sys.argv[sys.argv.index('--') + 1:])
first, last = (int(v) for v in args['frames'].split('-'))
with open(os.path.join(os.path.dirname(args['out']), 'blender.log'), 'a') as f: f.write(args['value'] + '\\n')
if args.get('value') == '13': sys.exit(1)
def png(path, w=48, h=48):
    def px(x, y): return [200, 20 + y * 2, 30] if y > h // 2 else [240, 240, 240] if 10 < x < 20 else [10, 10, 14]
    raw = b''.join(b'\\x00' + bytes(v for x in range(w) for v in px(x, y)) for y in range(h))
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(path, 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
for i in range(first, last + 1): png(os.path.join(args['out'], f'f{i:04d}.png'))
'''


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    fake = tmp_path / 'fake-blender'; fake.write_text(FAKE_BLENDER); fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv('RIGDECK_BLENDER', str(fake))
    monkeypatch.setattr(tank, 'FRAMES', 10)
    logo = tmp_path / 'logo.png'; img = QImage(64, 64, QImage.Format_ARGB32); img.fill(0xffffffff); img.save(str(logo))
    return tmp_path, logo


def renders(tmp_path):
    log = tmp_path / 'cache' / 'rigdeck' / 'tank' / 'blender.log'
    return log.read_text().split() if log.exists() else []


def test_segments_are_the_six_numbers_with_plain_labels():
    segs = tank.segments(SUMMARY, POSITIONS)
    assert [(s['key'], s['prefix'], s['value'], s['label']) for s in segs] == [
        ('shown', '', 2603, 'times shown on Google'), ('change', '+', 305, 'more than the 28 days before'),
        ('clicks', '', 5, 'clicks from Google'), ('searches', '', 180, 'searches you showed up for'),
        ('page-one', '', 17, 'searches on page one'), ('top-three', '', 8, 'searches in the top three')]
    assert {s['sub'] for s in segs} == {'28 days to Nov 3', 'times shown on Google'}
    assert all('—' not in s['label'] + s['sub'] for s in segs)
    assert len(tank.segments(SUMMARY)) == 3                                          # no position numbers: no position segments
    down = tank.segments({**SUMMARY, 'deltas': {'impressions': -40}})[1]
    assert (down['prefix'], down['value'], down['label']) == ('-', 40, 'fewer than the 28 days before')
    assert tank.segments({**SUMMARY, 'deltas': {}})[1]['key'] == 'clicks'


def test_render_key_changes_only_when_the_picture_would(studio):
    tmp_path, logo = studio
    seg = tank.segments(SUMMARY)[0]
    base = tank.render_key(seg, '#ff2f3f', logo, 384, 72)
    assert tank.render_key(dict(seg), '#FF2F3F', logo, 384, 72) == base
    assert tank.render_key({**seg, 'label': 'anything'}, '#ff2f3f', logo, 384, 72) == base           # labels are added afterwards
    assert tank.render_key({**seg, 'value': 2604}, '#ff2f3f', logo, 384, 72) != base
    assert tank.render_key(seg, '#16b8ff', logo, 384, 72) != base
    other = tmp_path / 'other.png'; QImage(8, 8, QImage.Format_ARGB32).save(str(other))
    assert tank.render_key(seg, '#ff2f3f', other, 384, 72) != base


def test_a_rendered_number_is_kept_and_a_failed_render_leaves_nothing(studio):
    tmp_path, logo = studio
    seg = tank.segments(SUMMARY)[0]
    folder = tank.render_segment(seg, '#ff2f3f', logo)
    assert len(list(folder.glob('f*.png'))) == 10 and renders(tmp_path) == ['2603']
    assert tank.render_segment(seg, '#ff2f3f', logo) == folder and renders(tmp_path) == ['2603']   # second time: from the cache
    with pytest.raises(ValueError, match='Blender did not finish'):
        tank.render_segment({**seg, 'value': 13}, '#ff2f3f', logo)
    assert not (tank.cache_dir() / tank.render_key({**seg, 'value': 13}, '#ff2f3f', logo, 384, 72)).exists()


def luminance(img, x0, y0, x1, y1):
    import numpy as np
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[y0:y1, x0 * 3:x1 * 3].reshape(y1 - y0, x1 - x0, 3) / 255
    c = np.where(a <= .03928, a / 12.92, ((a + .055) / 1.055) ** 2.4)
    return .2126 * c[..., 0] + .7152 * c[..., 1] + .0722 * c[..., 2]


def test_labels_keep_contrast_even_over_a_white_frame_and_vanish_while_the_number_moves(tmp_path):
    white = tmp_path / 'white.png'; img = QImage(384, 384, QImage.Format_RGB888); img.fill(0xffffff); img.save(str(white))
    settled = tank.finish(white, 'times shown on Google', '28 days to Nov 3', t=.5).convertToFormat(QImage.Format_RGB888)
    bare = tank.finish(white, '', '', t=.5).convertToFormat(QImage.Format_RGB888)
    # the brightest thing behind the label text must still give white text 4.5:1
    backing = tank.finish(white, ' ', ' ', t=.5).convertToFormat(QImage.Format_RGB888)   # the dark depth, with nothing written on it
    assert (1.05 / (luminance(backing, 50, 228, 270, 274).max() + .05)) >= 4.5             # across the width the longest label spans
    assert luminance(bare, 150, 130, 170, 150).min() > .9                 # the rest of the frame is untouched
    assert luminance(settled, 0, 0, 6, 6).max() < .01                     # outside the round screen is black
    diving = tank.finish(white, 'times shown on Google', '28 days to Nov 3', t=.0).convertToFormat(QImage.Format_RGB888)
    assert luminance(diving, 70, 228, 250, 274).min() > .9                 # no labels, no dark depth while the number is under


def test_assembled_clip_is_in_the_device_format(studio, tmp_path):
    _, logo = studio
    segs = tank.segments(SUMMARY)[:2]
    dirs = [tank.render_segment(s, '#ff2f3f', logo) for s in segs]
    out = tank.assemble(segs, dirs, tmp_path / 'clip')
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
            'stream=codec_name,width,height,pix_fmt,has_b_frames:format=duration', '-of', 'json', out]))
    assert probe['streams'][0] == {'codec_name': 'h264', 'width': 320, 'height': 320, 'pix_fmt': 'yuv420p', 'has_b_frames': 0}
    assert abs(float(probe['format']['duration']) - 20 / 25) < .1
    assert (tmp_path / 'clip' / 'preview.gif').exists() and (tmp_path / 'clip' / 'poster.png').exists()


def tank_home(home, studio, positions=POSITIONS, project='macdigital.ca'):
    tmp_path, logo = studio
    (home / 'projects.json').write_text(json.dumps([{'site': 'macdigital.ca', 'name': 'MacDigital', 'color': '#ff2f3f', 'logo': str(logo),
                                                    'snapshot': summary('macdigital.ca', 1, end='2026-10-31', start='2026-10-04')}]))
    numbers(home, [SUMMARY])
    script = home / 'positions.py'
    script.write_text(f'import json,sys\nprint(json.dumps({positions!r}))\nsys.exit({0 if positions else 2})\n')
    config = json.loads((home / 'studio-daily.json').read_text())
    config['tank'] = {'project': project, 'positions': [sys.executable, str(script)]}
    (home / 'studio-daily.json').write_text(json.dumps(config))
    return tmp_path


def test_daily_job_builds_the_tank_and_renders_only_what_changed(home, studio):
    tmp_path = tank_home(home, studio)
    cooler = FakeCooler(['daily-20261104-aaaaaa.mkv'])
    code, said = run(home, cooler)
    assert code == 0, said
    assert 'Numbers for the tank: 2,603 times shown on Google, +305 more than the 28 days before, 5 clicks from Google, 180 searches you showed up for, 17 searches on page one, 8 searches in the top three' in said
    assert sorted(renders(tmp_path)) == sorted(['2603', '305', '5', '180', '17', '8'])
    assert cooler.files == [f for f in cooler.files if f.startswith('daily-20261105-')] and cooler.playing == cooler.files
    state = json.loads((home / 'studio-daily-state.json').read_text())
    assert state['positions']['searches'] == 180
    # same numbers again: nothing rendered, nothing sent
    before = list(cooler.log)
    assert run(home, cooler)[0] == 0 and cooler.log == before and len(renders(tmp_path)) == 6
    # one number changes: one new render, a new clip
    numbers(home, [{**SUMMARY, 'current': {**SUMMARY['current'], 'clicks': 6}}])
    code, said = run(home, cooler)
    assert code == 0 and renders(tmp_path)[-1] == '6' and len(renders(tmp_path)) == 7


def test_daily_job_keeps_earlier_position_numbers_when_they_cannot_be_fetched(home, studio):
    tmp_path = tank_home(home, studio)
    cooler = FakeCooler()
    assert run(home, cooler)[0] == 0
    tank_home(home, studio, positions=None)
    numbers(home, [{**SUMMARY, 'current': {**SUMMARY['current'], 'clicks': 7}}])
    code, said = run(home, cooler)
    assert code == 0 and 'Using the position numbers fetched earlier' in said and '180 searches you showed up for' in said


def test_daily_job_names_a_missing_tank_project(home, studio):
    tank_home(home, studio, project='nobody.example')
    code, said = run(home, FakeCooler())
    assert code == 1 and "No project with numbers called 'nobody.example'" in said


def test_old_unused_renders_are_pruned_and_used_ones_kept(studio):
    tmp_path, logo = studio
    segs = tank.segments(SUMMARY)[:2]
    old, new = (tank.render_segment(s, '#ff2f3f', logo) for s in segs)
    stale = tank.cache_dir() / 'stale'; stale.mkdir(); os.utime(stale, (0, 0)); os.utime(old, (0, 0))
    tank.prune(keep=[new])
    assert new.exists() and not stale.exists() and not old.exists()
    fresh_unused = tank.cache_dir() / 'fresh'; fresh_unused.mkdir()
    tank.prune(keep=[new])
    assert fresh_unused.exists()                                           # not used today, but too recent to drop
