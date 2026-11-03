"""Screen Studio contract: local rendering, input bounds, data provenance and media format."""
import json
import os
import subprocess
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip("PySide6")
from PySide6.QtGui import QGuiApplication, QImage
from rigdeck.gui import studio

@pytest.fixture(scope='module', autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app

@pytest.mark.parametrize('changes', [{'size':0}, {'duration':100}, {'y':321}, {'color':'invalid'},
                                     {'text':'x'*65}, {'media':'/missing/image.png'}, {'effect':'unknown'}])
def test_validation(changes):
    with pytest.raises(ValueError): studio.validate(changes)

def test_literal_text_and_animation():
    d=studio.validate({'text':'Seann: 100% & "ICE"', 'subtitle':'雪 · AORUS'})
    a=studio.compose(d,0); b=studio.compose(d,2)
    assert not a.isNull() and a.size().width()==320
    assert a != b

def test_media_matches_device_contract(tmp_path):
    source=QImage(640,480,QImage.Format_RGB888); source.fill('#334455')
    source.save(str(tmp_path/'input.png'))
    output=studio.render({'duration':3,'media':str(tmp_path/'input.png')},tmp_path/'render')
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',output]))
    stream=data['streams'][0]
    assert (stream['codec_name'],stream['width'],stream['height'])==('h264',320,320)
    assert stream['profile']=='Main' and stream['level']==31 and stream['has_b_frames']==0
    assert stream['r_frame_rate']=='25/1'
    assert abs(float(data['format']['duration'])-3)<.1
    assert (tmp_path/'render'/'preview.gif').stat().st_size>100

def test_invalid_snapshot_never_replaces_valid_data(tmp_path, monkeypatch):
    monkeypatch.setattr(studio,'ROOT',tmp_path)
    backend=studio.ScreenStudio()
    path=tmp_path/'invalid.json'; path.write_text(json.dumps({'siteUrl':'sc-domain:other.example'}))
    backend.importStats(studio.QUrl.fromLocalFile(str(path)).toString())
    assert 'Could not import' in backend.error
    assert not (tmp_path/'traffic-snapshot.json').exists()

def test_draft_roundtrip_invalidates_ready_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(studio,'ROOT',tmp_path)
    backend=studio.ScreenStudio(); backend._output='/tmp/render.mkv'
    backend.edit('text','ICE "quoted"\nline')
    assert not backend.ready
    assert studio.ScreenStudio().draft['text']=='ICE "quoted"\nline'

def test_render_failure_is_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(studio,'ROOT',tmp_path)
    backend=studio.ScreenStudio(); backend.edit('color','invalid'); backend.render()
    assert 'valid color' in backend.error and not backend.busy and not backend.ready


def test_portfolio_render_duration_and_distinct_projects(tmp_path):
    snapshot={'siteUrl':'sc-domain:one.example','range':{'startDate':'2026-10-01','endDate':'2026-10-28','days':28},'current':{'clicks':2,'impressions':20,'ctr':10},'dailyRows':[]}
    projects=[{'site':'one.example','name':'One','snapshot':snapshot}, {'site':'two.example','name':'Two','snapshot':{**snapshot,'siteUrl':'sc-domain:two.example','current':{'clicks':7,'impressions':35,'ctr':20}}}]
    output=studio.render_projects({**studio.DEFAULT,'preset':'Projects','duration':3},tmp_path/'portfolio',projects)
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',output]))
    assert abs(float(data['format']['duration'])-6)<.1
    assert QImage(str(tmp_path/'portfolio/0/poster.png')) != QImage(str(tmp_path/'portfolio/1/poster.png'))


def test_live_unknown_metrics_are_not_displayed_as_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(studio,'ROOT',tmp_path)
    backend=studio.ScreenStudio(); backend._projects=[{'site':'one.example','name':'One'}]
    unavailable=backend.live_frame(0)
    backend._live_data={'sites':[{'site':'one.example','requests':0,'bytes':0,'cachePct':None,'serverErrors':0}]}
    real_zero=backend.live_frame(0)
    assert unavailable != real_zero


def test_studio_upload_selects_only_new_clip_and_clears_legacy_text(monkeypatch):
    from types import SimpleNamespace
    from rigdeck.modules.waterforce import qt
    calls=[]
    device=SimpleNamespace(storage_free_kb=lambda:10000,upload_media=lambda *a:calls.append('upload'),send=lambda b:calls.append(b),save=lambda:calls.append('save'))
    screen=SimpleNamespace(files=['old.mkv','new.mkv'],write=lambda c,files,playing:calls.append((files,playing)))
    monkeypatch.setattr(qt.media,'convert',lambda p:b'video')
    monkeypatch.setattr(qt.media,'make_preview',lambda *a:None)
    monkeypatch.setattr(qt,'add_to_carousel',lambda *a:screen)
    monkeypatch.setattr(qt,'run_async',lambda fn,done,error:done(fn()))
    backend=SimpleNamespace(_busy='',_set_busy=lambda *a:None,_with=lambda fn:fn(device),_apply_screen=lambda *a:None,toast=SimpleNamespace(emit=lambda m:None))
    qt.CoolerBackend.upload(backend,'/tmp/new.mkv',exclusive=True)
    assert (['old.mkv','new.mkv'],['new.mkv']) in calls
    assert b'\xc0\x00\x00\x00' in calls
    assert calls[-1]=='save'
