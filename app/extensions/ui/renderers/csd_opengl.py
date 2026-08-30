"""Optional OpenGL CSD surface renderer (WP-07).

Only loads when pyqtgraph.opengl and PyOpenGL are importable; every failure
mode reports unsupported so callers fall back to the 2D renderer.
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

    def render(self, plot_widget, csd_result, mode: str = 'A') -> None:
        gl = self._gl
        plot_widget.clear()
        mag = np.asarray(csd_result.magnitude_db, dtype=float)
        nf, nt = mag.shape
        # downsample to keep the mesh light
        step_f = max(1, nf // 120)
        step_t = max(1, nt // 90)
        z = mag[::step_f, ::step_t].T.copy()
        x = np.linspace(csd_result.freqs[0], csd_result.freqs[-1], z.shape[1])
        y = np.asarray(csd_result.times_ms, dtype=float)[::step_t].copy()
        xg, yg = np.meshgrid(np.log10(x), y)
        z_shift = z - z.min() + 1.0
        colors = _height_colors(z, cfg_dyn=csd_result.cfg.dynamic_range_db)
        mesh = gl.GLMeshItem(vertexes=_mesh_vertices(xg, yg, z_shift),
                             facecolors=colors, drawEdges=True,
                             edgeColor=(0.2, 0.2, 0.2, 0.3), smooth=False)
        plot_widget.addItem(mesh)


def _mesh_vertices(xg: np.ndarray, yg: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Build a vertex/face grid for GLMeshItem from a height field."""
    ny, nx = z.shape
    verts = np.column_stack([xg.ravel(), yg.ravel(), z.ravel()])
    idx = np.arange(ny * nx).reshape(ny, nx)
    faces = []
    for r in range(ny - 1):
        for c in range(nx - 1):
            a, b = idx[r, c], idx[r, c + 1]
            d, e = idx[r + 1, c], idx[r + 1, c + 1]
            faces.append([a, b, e])
            faces.append([a, e, d])
    return verts, np.array(faces)


def _height_colors(z: np.ndarray, cfg_dyn: float) -> np.ndarray:
    dyn = max(cfg_dyn, 1.0)
    frac = np.clip((z + dyn) / dyn, 0.0, 1.0)
    colors = np.zeros((*z.shape, 4))
    colors[..., 0] = 0.36 + 0.3 * frac
    colors[..., 1] = 0.61 * frac + 0.15
    colors[..., 2] = 0.88 - 0.4 * frac
    colors[..., 3] = 1.0
    return colors.reshape(-1, 4)
