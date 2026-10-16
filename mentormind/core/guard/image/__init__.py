"""Image side of the outbound guard: anonymise frames before they go to a cloud VLM.

One module per technique; ``face_blur`` (YuNet + pixelation) is the first. Not imported by
``mentormind.core.guard`` itself, so the text guards never pull in OpenCV.
"""

from mentormind.core.guard.image.face_blur import FaceBlurError, FaceBlurrer, ImageGuardPolicy

__all__ = ["FaceBlurError", "FaceBlurrer", "ImageGuardPolicy"]
