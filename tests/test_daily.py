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
    def exclusive(self):
        import contextlib
        return contextlib.nullcontext(self)
    def settle(self, note=None): self.log.append('settle')
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def list_media(self): return list(self.files)
    def storage_free_kb(self): return self.free_kb
    def upload_media(self, data, name, progress=None, note=None):
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
    config = json.loads((home/'studio-daily.json').read_text()) if (home/'studio-daily.json').exists() else {}
    (home/'studio-daily.json').write_text(json.dumps({**config, 'command': [sys.executable, str(script)]}))


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
    gone = cooler.log.index(('delete', 'daily-20261104-aaaaaa.mkv'))
    assert cooler.log.index(uploads[0]) < gone and 'settle' in cooler.log[cooler.log.index(uploads[0]):gone]  # new first, a quiet gap, then remove
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
    first = cooler.files[0]
    code, said = run(home, cooler, force=True)                                  # forced: a second clip replaces the first
    assert code == 0 and len(cooler.files) == 1 and cooler.files[0] != first and cooler.playing == cooler.files
    assert f'Removed {first}' in said


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
    assert 'Set the numbers command' in run(home, cooler)[1]


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
    assert cooler.files == ['daily-20261104-aaaaaa.mkv'] and ('delete', 'daily-20261104-aaaaaa.mkv') not in cooler.log
    assert (home/'projects.json').read_text() == before and not (home/'studio-daily-state.json').exists()


@pytest.mark.parametrize('misses,answers', [(2, True), (4, False)])
def test_free_space_is_asked_again_while_the_cooler_settles(monkeypatch, misses, answers):
    from rigdeck.modules.waterforce import device
    monkeypatch.setattr(device.time, 'sleep', lambda s: None)
    cooler, asked = object.__new__(device.Cooler), []
    def query(payload, timeout=1.0, match=1):
        asked.append(payload)
        if len(asked) <= misses: raise device.CoolerError('no reply to command 0xfa')
        return bytes([0x99, 0xfa, 3]) + (44000).to_bytes(3, 'little') + bytes(250)
    cooler.query = query
    if answers:
        assert cooler.storage_free_kb() == 44000 and len(asked) == 3
    else:
        with pytest.raises(device.CoolerError): cooler.storage_free_kb()
        assert len(asked) == 4


class Wire:
    """A real driver object talking to a pretend cooler, to test what it sends and when."""
    def __init__(self, monkeypatch, tmp_path, listed_after=1, answers_free_space=True):
        from rigdeck.modules.waterforce import device
        monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path)); monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
        self.device, self.slept, self.sent, self.lists = device, [], [], 0
        monkeypatch.setattr(device.time, 'sleep', self.slept.append)
        self.cooler = c = object.__new__(device.Cooler)
        c.fd = os.open(os.devnull, os.O_RDWR)
        real_send = device.Cooler.send
        def send(payload):
            c._back_off_during_upload(); self.sent.append(payload[:2])
        def list_media():
            self.lists += 1
            return ['old.mkv'] + (['new.mkv'] if self.lists >= listed_after else [])
        def free():
            if not answers_free_space: raise device.CoolerError('no reply to command 0xfa')
            return 40000
        c.send, c.list_media, c.storage_free_kb = send, list_media, free


def test_upload_holds_the_cooler_alone_and_waits_for_it_to_list_the_clip(monkeypatch, tmp_path):
    w = Wire(monkeypatch, tmp_path, listed_after=3)
    other = object.__new__(w.device.Cooler)                       # another rigdeck program
    seen = []
    def progress(done, total):
        try: other._back_off_during_upload(); seen.append('sent')
        except w.device.CoolerError as e: seen.append(str(e))
    w.cooler.upload_media(b'x' * (w.device.CHUNK * 2 + 10), 'new.mkv', progress)
    assert seen == ['the cooler is busy storing a clip'] * 3           # everyone else backs off during the transfer
    other._back_off_during_upload()                                # and is let through again afterwards
    assert [p[0] for p in w.sent] == [0xF1, 0xF2, 0xF2, 0xF2, 0xF1] and w.lists == 3
    assert w.device.last_flash() > 0


def test_upload_waits_out_the_quiet_time_after_the_last_stored_clip(monkeypatch, tmp_path):
    w = Wire(monkeypatch, tmp_path)
    w.device.mark_flash(); said = []
    w.cooler.upload_media(b'x', 'new.mkv', note=said.append)
    assert said and said[0].startswith('Letting the cooler settle')
    assert any(100 < s <= w.device.SETTLE for s in w.slept)


def test_upload_writes_nothing_when_the_cooler_is_not_answering(monkeypatch, tmp_path):
    w = Wire(monkeypatch, tmp_path, answers_free_space=False)
    with pytest.raises(w.device.CoolerError): w.cooler.upload_media(b'x', 'new.mkv')
    assert w.sent == [] and w.device.last_flash() == 0


def test_upload_that_never_shows_up_is_reported_not_assumed(monkeypatch, tmp_path):
    w = Wire(monkeypatch, tmp_path, listed_after=10**9)
    clock = iter(range(0, 10**6, 5))
    monkeypatch.setattr(w.device.time, 'monotonic', lambda: next(clock))
    with pytest.raises(w.device.CoolerError, match='did not confirm new.mkv'): w.cooler.upload_media(b'x', 'new.mkv')
    w.cooler._back_off_during_upload()                             # the hold is released even on failure
