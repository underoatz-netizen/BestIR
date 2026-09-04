"""Optional OpenGL CSD surface renderer.

This module deliberately does not import ``pyqtgraph.opengl`` at module load:
the 2D CSD view remains usable on installations without PyOpenGL.
"""
from __future__ import annotations

import numpy as np


class OpenGLCsdRenderer:
    name = 'opengl'

    def __init__(self):
        import pyqtgraph.opengl as gl
        self._gl = gl

    def supports(self) -> bool:
        try:
            import OpenGL.GL  # noqa: F401
            return True
        except Exception:
            return False

    def create_view(self, parent=None):
        """Create the GL-only canvas; callers may fall back if this fails."""
        view = self._gl.GLViewWidget(parent=parent)
        if hasattr(view, 'setBackgroundColor'):
            view.setBackgroundColor((24, 26, 31, 255))
        return view

    def render(self, view, csd_result, mode: str = 'A') -> bool:
        """Render a valid mesh and return whether an item was added.

        Empty, non-finite, or one-dimensional input is not a GL capability
        failure.  It is simply left blank so a bad result cannot crash Qt.
        """
        data = _mesh_data(csd_result)
        view.clear()
        if data is None:
            return False
        vertexes, faces, face_colors, bounds = data
        mesh = self._gl.GLMeshItem(
            vertexes=vertexes, faces=faces, faceColors=face_colors,
            drawEdges=True, edgeColor=(0.2, 0.2, 0.2, 0.3), smooth=False)
        view.addItem(mesh)
        _set_camera_bounds(view, bounds)
        return True


def _mesh_data(csd_result):
    """Return ``(vertexes, faces, faceColors, bounds)`` or ``None`` safely."""
    mag = np.asarray(getattr(csd_result, 'magnitude_db', ()), dtype=float)
    freqs = np.asarray(getattr(csd_result, 'freqs', ()), dtype=float)
    times = np.asarray(getattr(csd_result, 'times_ms', ()), dtype=float)
    if (mag.ndim != 2 or mag.shape[0] < 2 or mag.shape[1] < 2 or
            freqs.ndim != 1 or times.ndim != 1 or
            len(freqs) != mag.shape[0] or len(times) != mag.shape[1]):
        return None

    step_f = max(1, mag.shape[0] // 120)
    step_t = max(1, mag.shape[1] // 90)
    z = mag[::step_f, ::step_t].T.copy()  # rows=time, columns=frequency
    x = freqs[::step_f]
    y = times[::step_t]
    if (z.shape[0] < 2 or z.shape[1] < 2 or not np.all(np.isfinite(x)) or
            not np.all(np.isfinite(y)) or np.any(x <= 0)):
        return None
    finite = np.isfinite(z)
    if not finite.any():
        return None
    # Keep isolated NaN/inf cells from producing undefined GL geometry.
    z[~finite] = float(np.median(z[finite]))
    xg, yg = np.meshgrid(np.log10(x), y)
    z_shift = z - float(np.min(z)) + 1.0
    vertexes, faces = _mesh_geometry(xg, yg, z_shift)
    if faces.size == 0:
        return None
    cfg = getattr(csd_result, 'cfg', None)
    vertex_colors = _height_colors(z, getattr(cfg, 'dynamic_range_db', 60.0))
    # GLMeshItem's faceColors is one RGBA colour per triangular face.
    face_colors = vertex_colors[faces].mean(axis=1).astype(np.float32, copy=False)
    bounds = (float(xg.min()), float(xg.max()), float(yg.min()), float(yg.max()),
              float(z_shift.min()), float(z_shift.max()))
    return vertexes, faces, face_colors, bounds


def _mesh_geometry(xg: np.ndarray, yg: np.ndarray, z: np.ndarray):
    """Build separate ``(N, 3)`` vertexes and ``(M, 3)`` triangular faces."""
    if xg.shape != yg.shape or xg.shape != z.shape or z.ndim != 2:
        raise ValueError('mesh coordinate grids must be equally shaped 2D arrays')
    ny, nx = z.shape
    if ny < 2 or nx < 2:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32)
    vertexes = np.column_stack((xg.ravel(), yg.ravel(), z.ravel())).astype(np.float32)
    idx = np.arange(ny * nx, dtype=np.uint32).reshape(ny, nx)
    a, b = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
    d, e = idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    faces = np.empty((a.size * 2, 3), dtype=np.uint32)
    faces[0::2] = np.column_stack((a, b, e))
    faces[1::2] = np.column_stack((a, e, d))
    return vertexes, faces


def _height_colors(z: np.ndarray, cfg_dyn: float) -> np.ndarray:
    """Return one finite RGBA colour per vertex, shape ``(N, 4)``."""
    dyn = max(float(cfg_dyn), 1.0)
    frac = np.clip((z + dyn) / dyn, 0.0, 1.0)
    colors = np.empty((*z.shape, 4), dtype=np.float32)
    colors[..., 0] = 0.36 + 0.3 * frac
    colors[..., 1] = 0.61 * frac + 0.15
    colors[..., 2] = 0.88 - 0.4 * frac
    colors[..., 3] = 1.0
    return colors.reshape(-1, 4)


def _set_camera_bounds(view, bounds) -> None:
    """Use data-derived framing without relying on PlotWidget APIs."""
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    span = max(xmax - xmin, ymax - ymin, zmax - zmin, 1.0)
    view.setCameraPosition(distance=span * 2.2, elevation=28, azimuth=-48)
