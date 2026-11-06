"""Once-a-day cooler update: what reaches the cooler, what is removed, and what happens when a step fails."""
import json
import os
import subprocess
import sys
from datetime import date
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip("PySide6")
from rigdeck.gui import daily, studio
from rigdeck.modules import waterforce


def summary(site, clicks, end='2026-11-02', start='2026-10-06'):
    return {'siteUrl': 'sc-domain:' + site, 'range': {'startDate': start, 'endDate': end, 'days': 28},
            'current': {'clicks': clicks, 'impressions': clicks * 10, 'ctr': 10.0, 'avgPosition': 12.0},
            'dailyRows': [{'date': '2026-10-06', 'clicks': 0, 'impressions': 3, 'ctr': 0, 'position': 9.0}]}


class FakeCooler:
    """Remembers files, play order and every command, like the real storage does."""
    def __init__(self, files=(), free_kb=40000, fail_upload=False):
        self.files, self.playing, self.free_kb, self.fail_upload = list(files), list(files[:1]), free_kb, fail_upload
        self.log, self.opened = [], 0
    def __call__(self): self.opened += 1; return self
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def list_media(self): return list(self.files)
    def storage_free_kb(self): return self.free_kb
    def upload_media(self, data, name, progress=None):
        if self.fail_upload: raise OSError('cable unplugged')
        self.files.append(name); self.log.append(('upload', name, len(data)))
    def file_ids(self): return list(self.files), {n: i + 1 for i, n in enumerate(self.files)}
    def carousel(self): return [self.files.index(n) for n in self.playing if n in self.files], 5
    def set_carousel(self, order_ids, playing, interval):
        names = list(self.files); self.files = [names[i - 1] for i in order_ids]
        self.playing = [self.files[p] for p in playing]; self.log.append(('carousel', list(self.playing)))
    def delete_media(self, name): self.files.remove(name); self.playing = [n for n in self.playing if n != name]; self.log.append(('delete', name))
    def send(self, payload): self.log.append(('send', payload))
    def save(self): self.log.append('save')


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, 'ROOT', tmp_path)
    monkeypatch.setattr(waterforce.time, 'sleep', lambda s: None)
    projects = [{'site': 'one.example', 'name': 'One', 'snapshot': summary('one.example', 1, end='2026-10-31', start='2026-10-04')},
                {'site': 'two.example', 'name': 'Two', 'snapshot': summary('two.example', 2, end='2026-10-31', start='2026-10-04')}]
    (tmp_path/'projects.json').write_text(json.dumps(projects))
    (tmp_path/'studio-draft.json').write_text(json.dumps({'duration': 3, 'effect': 'Still'}))
    return tmp_path


def numbers(home, sites, code=0):
    script = home/'numbers.py'
    script.write_text(f'import json,sys\nprint(json.dumps({{"sites": {sites!r}}}))\nsys.exit({code})\n')
    (home/'studio-daily.json').write_text(json.dumps({'command': [sys.executable, str(script)]}))


def run(home, cooler, **kw):
    said = []
    code = daily.run(today=date(2026, 11, 5), open_cooler=cooler, say=said.append, **kw)
    return code, ' | '.join(said)


def shown(home):
    return [(p['name'], p['snapshot']['current']['clicks'], p['snapshot']['range']['endDate']) for p in json.loads((home/'projects.json').read_text())]


def test_sends_fresh_numbers_and_removes_only_its_own_earlier_clip(home):
    numbers(home, [summary('one.example', 11), summary('two.example', 22)])
    cooler = FakeCooler(['holiday.mkv', 'daily-20261104-aaaaaa.mkv', 'studio-1234abcd.mkv'])
    code, said = run(home, cooler)
    assert code == 0, said
    new = [f for f in cooler.files if f.startswith('daily-20261105-')]
    assert len(new) == 1 and new[0].endswith('.mkv')
    assert cooler.files == ['holiday.mkv', 'studio-1234abcd.mkv', new[0]]      # the owner's clips stay
    assert cooler.playing == new                                               # only the new clip plays
    assert ('send', b'\xc0\x00\x00\x00') in cooler.log
    uploads = [e for e in cooler.log if e[0] == 'upload']
    assert len(uploads) == 1 and uploads[0][2] > 10_000
    assert cooler.log.index(uploads[0]) < cooler.log.index(('delete', 'daily-20261104-aaaaaa.mkv'))  # new first, then remove
    assert shown(home) == [('One', 11, '2026-11-02'), ('Two', 22, '2026-11-02')]
    state = json.loads((home/'studio-daily-state.json').read_text())
    assert state['clip'] == new[0] and state['updated'] == ['One', 'Two']
    assert 'Removed daily-20261104-aaaaaa.mkv' in said


def test_does_not_write_the_cooler_again_when_nothing_changed(home):
    numbers(home, [summary('one.example', 11), summary('two.example', 22)])
    cooler = FakeCooler()
    assert run(home, cooler)[0] == 0
    before = list(cooler.log)
    code, said = run(home, cooler)
    assert code == 0 and cooler.log == before and 'nothing was sent' in said
    assert run(home, cooler, force=True)[1].count('already on the cooler') == 1   # same day, same picture: refuse a duplicate


def test_one_unreadable_site_keeps_its_dated_numbers_while_the_rest_update(home):
    numbers(home, [summary('one.example', 11), {'site': 'two.example', 'error': 'cannot read'}])
    cooler = FakeCooler()
    code, said = run(home, cooler)
    assert code == 0
    assert shown(home) == [('One', 11, '2026-11-02'), ('Two', 2, '2026-10-31')]
    assert 'Kept earlier numbers for Two: no numbers returned' in said


@pytest.mark.parametrize('bad', [
    {**summary('one.example', 5), 'current': {'clicks': -1, 'impressions': 5, 'ctr': 1}},
    {**summary('one.example', 5), 'range': {'startDate': '2026-10-06', 'endDate': '2026-11-02', 'days': 7}},
    summary('one.example', 5, end='2026-10-01', start='2026-09-04'),          # older than what is shown
    {'siteUrl': 'sc-domain:one.example'},
])
def test_refuses_unusable_or_older_numbers(home, bad):
    numbers(home, [bad, summary('two.example', 22)])
    run(home, FakeCooler())
    assert shown(home)[0] == ('One', 1, '2026-10-31')
    assert shown(home)[1] == ('Two', 22, '2026-11-02')


def test_failed_fetch_changes_nothing_after_the_first_send(home):
    numbers(home, [summary('one.example', 11), summary('two.example', 22)])
    cooler = FakeCooler()
    run(home, cooler)
    before, files = list(cooler.log), (home/'projects.json').read_text()
    numbers(home, [], code=3)
    code, said = run(home, cooler)
    assert code == 1 and cooler.log == before and (home/'projects.json').read_text() == files
    assert 'The numbers command failed' in said
    (home/'studio-daily.json').write_text('{}')
    assert 'Set "command"' in run(home, cooler)[1]


def test_dry_run_builds_a_device_ready_clip_and_touches_nothing(home):
    numbers(home, [summary('one.example', 11), summary('two.example', 22)])
    cooler, before = FakeCooler(), (home/'projects.json').read_text()
    code, said = run(home, cooler, dry_run=True, out=home/'preview')
    assert code == 0 and cooler.opened == 0 and cooler.log == []
    assert (home/'projects.json').read_text() == before and not (home/'studio-daily-state.json').exists()
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
            'stream=codec_name,width,height,pix_fmt,has_b_frames:format=duration', '-of', 'json', str(home/'preview/clip.mkv')]))
    assert probe['streams'][0] == {'codec_name': 'h264', 'width': 320, 'height': 320, 'pix_fmt': 'yuv420p', 'has_b_frames': 0}
    assert abs(float(probe['format']['duration']) - 6) < .1
    assert (home/'preview/poster.png').exists() and 'Nothing was sent' in said


@pytest.mark.parametrize('cooler', [FakeCooler(['daily-20261104-aaaaaa.mkv'], fail_upload=True),
                                    FakeCooler(['daily-20261104-aaaaaa.mkv'], free_kb=1)])
def test_a_failed_send_keeps_the_old_clip_and_the_old_numbers(home, cooler):
    numbers(home, [summary('one.example', 11), summary('two.example', 22)])
    before = (home/'projects.json').read_text()
    code, said = run(home, cooler)
    assert code == 1 and 'Could not send the clip' in said
    assert cooler.files == ['daily-20261104-aaaaaa.mkv'] and not any(e[0] == 'delete' for e in cooler.log if isinstance(e, tuple))
    assert (home/'projects.json').read_text() == before and not (home/'studio-daily-state.json').exists()
