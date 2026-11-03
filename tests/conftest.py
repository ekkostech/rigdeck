"""Use one GUI-capable Qt application for core and rendering tests alike."""
import os
import pytest

@pytest.fixture(scope='session', autouse=True)
def qt_session():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        yield
        return
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app
