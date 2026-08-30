"""CSD renderer interface (WP-07).

`CsdRenderer` implementations draw a CSDResult. The OpenGL renderer is
optional; when pyqtgraph.opengl/PyOpenGL is unavailable it reports
unsupported and the caller falls back to the 2D renderer. The application
must never fail because 3D acceleration is missing.
"""
from __future__ import annotations


class CsdRenderer:
    name = 'base'

    def supports(self) -> bool:
        raise NotImplementedError

    def render(self, plot_widget, csd_result, mode: str = 'A') -> None:
        raise NotImplementedError


def try_opengl_renderer():
    """Return an OpenGL renderer instance, or None when unsupported."""
    try:
        import pyqtgraph.opengl  # noqa: F401
        import OpenGL.GL        # noqa: F401
    except Exception:
        return None
    try:
        from .csd_opengl import OpenGLCsdRenderer
        renderer = OpenGLCsdRenderer()
        return renderer if renderer.supports() else None
    except Exception:
        return None
