"""Video capture, segmentation and transcript (spec 03).

``probe`` → ``segmenters`` → ``postprocess`` → ``media`` → ``transcribe``, run in order by
``VideoCapturePipeline`` (FR-09); ``store`` keeps the files. Light to import: OpenCV, MediaPipe,
PySceneDetect and faster-whisper are loaded only by the step that needs them. ``align_transcript``
(FR-08) is what spec 04 imports from this package by name (``SPEC03_MODULE``).
"""

from mentormind.capture.video.align import align_transcript
from mentormind.capture.video.pipeline import CaptureResult, StageProgress, VideoCapturePipeline
from mentormind.capture.video.probe import probe_video, video_id_for

__all__ = ["CaptureResult", "StageProgress", "VideoCapturePipeline", "align_transcript", "probe_video", "video_id_for"]
