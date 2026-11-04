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
    backend._live_data={'start':'2026-11-03T12:00:00Z','end':'2026-11-03T12:15:00Z','sites':[{'site':'one.example','requests':0,'bytes':0,'cachePct':None,'serverErrors':0}]}
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


def test_minute_history_preserves_partial_edges_and_real_zeros():
    from rigdeck.gui.livecanvas import minute_history
    report={'start':'2026-11-03T12:00:30Z','end':'2026-11-03T12:15:30Z'}
    record={'series':[{'at':'2026-11-03T12:00:00Z','value':2},{'at':'2026-11-03T12:15:00Z','value':4}]}
    history=minute_history(report,record)
    assert len(history)==16
    assert history[0][1]==2 and history[-1][1]==4
    assert sum(v for _,v in history)==6
    assert all(v==0 for _,v in history[1:-1])
    assert minute_history(report,{'error':'Disconnected'})==[]
    assert len(minute_history({**report,'end':'2026-11-03T12:15:00Z'},{}))==15


def test_live_history_only_animates_when_measured_data_allows():
    from rigdeck.gui.livecanvas import draw
    project={'site':'example.com','name':'Example'}
    record={'requests':4,'bytes':1024,'cachePct':50,'serverErrors':0,'series':[{'at':'2026-11-03T12:05:00Z','value':4}]}
    report={'start':'2026-11-03T12:00:00Z','end':'2026-11-03T12:15:00Z','sites':[record]}
    def frame(t, data=record, freshness='UPDATED · 5s AGO', still=False):
        return draw(project,report,data,t,6,freshness,still)
    assert frame(0)!=frame(3)
    assert frame(0,still=True)==frame(3,still=True)
    assert frame(0,freshness='STALE · 200s AGO')==frame(3,freshness='STALE · 200s AGO')
    zero={**record,'requests':0,'series':[]}
    assert frame(0,zero)==frame(3,zero)
    assert frame(0,{'error':'Disconnected'})==frame(3,{'error':'Disconnected'})


def test_replay_ends_on_the_real_total_at_the_real_water_level():
    from rigdeck.gui.livecanvas import draw
    project={'site':'example.com','name':'Example'}
    record={'requests':4,'bytes':1024,'cachePct':50,'serverErrors':0,'series':[{'at':'2026-11-03T12:05:00Z','value':4}]}
    report={'start':'2026-11-03T12:00:00Z','end':'2026-11-03T12:15:00Z','sites':[record]}
    held=draw(project,report,record,5.4,6,'Updated 5s ago')
    assert held==draw(project,report,record,0,6,'Updated 5s ago',True)
    assert draw(project,report,record,1,6,'Updated 5s ago')!=held


def test_logo_tint_recolours_the_mark_and_keeps_its_shape(tmp_path):
    from PySide6.QtGui import QColor
    from PySide6.QtCore import Qt
    from rigdeck.gui.livecanvas import load_logo
    mark=QImage(40,20,QImage.Format_ARGB32); mark.fill(Qt.transparent)
    for x in range(20):
        for y in range(20): mark.setPixelColor(x,y,QColor('#0b2466'))
    mark.save(str(tmp_path/'mark.png'))
    logo=load_logo(str(tmp_path/'mark.png'),40,20,'#ffffff')
    assert logo.pixelColor(5,5)==QColor('#ffffff')
    assert logo.pixelColor(35,5).alpha()==0
    assert load_logo(str(tmp_path/'mark.png'),40,20).pixelColor(5,5)==QColor('#0b2466')
    assert load_logo(str(tmp_path/'missing.png'),40,20).isNull()
    assert load_logo('',40,20).isNull()


def live_report(age=5, sites=('one.example','two.example')):
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    record=lambda site:{'site':site,'requests':3,'bytes':2048,'cachePct':50,'serverErrors':0,
                        'series':[{'at':(now-timedelta(minutes=9)).strftime('%Y-%m-%dT%H:%M:00Z'),'value':3}]}
    return {'start':(now-timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M:%SZ'),'end':now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'fetchedAt':(now-timedelta(seconds=age)).isoformat(),'sites':[record(s) for s in sites]}


def test_live_clip_is_one_rotation_in_the_device_format(tmp_path):
    projects=[{'site':'one.example','name':'One','color':'#3f72ff'},{'site':'two.example','name':'Two','color':'#ff2f3f'}]
    output=studio.render_live(studio.validate({'preset':'Live projects','duration':3}),tmp_path/'live',projects,live_report())
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',output]))
    stream=data['streams'][0]
    assert (stream['codec_name'],stream['width'],stream['height'])==('h264',320,320)
    assert stream['profile']=='Main' and stream['level']==31 and stream['has_b_frames']==0
    assert abs(float(data['format']['duration'])-6)<.1
    assert (tmp_path/'live'/'preview.gif').stat().st_size>100 and (tmp_path/'live'/'poster.png').exists()


@pytest.mark.parametrize('report',[{},{'fetchedAt':None},live_report(age=600),
                                   {**live_report(),'sites':[{'site':'one.example','error':'Disconnected'}]}])
def test_live_clip_refuses_missing_stale_or_unusable_numbers(tmp_path,report):
    projects=[{'site':'one.example','name':'One'}]
    with pytest.raises(ValueError,match='Refresh Cloudflare now'):
        studio.render_live(studio.validate({'preset':'Live projects','duration':3}),tmp_path,projects,report)


def test_live_mode_builds_a_clip_that_can_be_sent(tmp_path,monkeypatch):
    monkeypatch.setattr(studio,'ROOT',tmp_path)
    monkeypatch.setattr(studio,'run_async',lambda fn,done,error:done(fn()))
    backend=studio.ScreenStudio(); backend.edit('preset','Live projects'); backend.edit('duration',3)
    backend._projects=[{'site':'one.example','name':'One'}]; backend._live_data=live_report(sites=('one.example',))
    backend.render()
    assert backend.error=='' and backend.ready and backend.output.endswith('.mkv')
    backend.clearPreview()
    assert not backend.ready


def test_live_page_offers_build_and_send(tmp_path,monkeypatch):
    from PySide6.QtCore import Property, QObject, QUrl, Signal
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from rigdeck.gui.studiopreview import StudioPreview
    from rigdeck.gui.theme import Theme
    class Cooler(QObject):
        changed=Signal()
        busy=Property(str,lambda s:'',notify=changed)
        connected=Property(bool,lambda s:True,notify=changed)
    class State(QObject):
        changed=Signal()
        reduceMotion=Property(bool,lambda s:True,notify=changed)
    monkeypatch.setattr(studio,'ROOT',tmp_path)
    backend=studio.ScreenStudio(); backend.edit('preset','Live projects')
    theme,cooler,state=Theme('ice'),Cooler(),State()
    engine=QQmlApplicationEngine()
    qml=os.path.join(os.path.dirname(studio.__file__),'qml')
    engine.addImportPath(qml); engine.addImageProvider('studio',StudioPreview(backend))
    context=engine.rootContext()
    for name,value in (('theme',theme),('cooler',cooler),('appState',state),('screenStudio',backend)):
        context.setContextProperty(name,value)
    component=QQmlComponent(engine,QUrl.fromLocalFile(os.path.join(qml,'pages','StudioPage.qml')))
    page=component.create(context)
    assert page is not None,component.errorString()
    def button(text):
        def walk(item):
            yield item
            for child in item.childItems(): yield from walk(child)
        return next(i for i in walk(page) if i.property('text')==text and i.property('highlighted') is not None)
    assert button('Build preview').property('enabled')
    assert not button('Send to cooler').property('enabled')
    backend._output='/tmp/built.mkv'; backend.changed.emit()
    assert button('Send to cooler').property('enabled')
    assert button('Back to live').property('visible')

