"""Live local preview without video re-encoding or cooler flash writes."""
import time
from PySide6.QtQuick import QQuickImageProvider

class StudioPreview(QQuickImageProvider):
    def __init__(self,studio):
        super().__init__(QQuickImageProvider.Image)
        self.studio=studio
        self.started=time.monotonic()
    def requestImage(self,identifier,size,requestedSize):
        try:
            frame=self.studio.live_frame(time.monotonic()-self.started, still='/still/' in identifier)
        except (ValueError, TypeError, KeyError, OSError):
            from .studio import compose, DEFAULT
            frame=compose({**DEFAULT,'text':'PREVIEW UNAVAILABLE','subtitle':'Check project configuration'})
        size.setWidth(frame.width());size.setHeight(frame.height())
        return frame
