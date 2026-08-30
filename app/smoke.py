"""Command-line smoke test: analyze a folder and print a metrics table.

Usage: python -m app.smoke "<ir folder>" [--limit N]
"""
from __future__ import annotations

import sys
import time

from .core.cache import LibraryCache
from .core.scanner import scan_library


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    folder = argv[1]
    limit = int(argv[argv.index('--limit') + 1]) if '--limit' in argv else 25

    t0 = time.perf_counter()
    cache = LibraryCache('.bestir_cache.json')
    results = scan_library([folder], cache)
    dt = time.perf_counter() - t0

    print(f'analyzed {len(results)} files in {dt:.1f}s '
          f'({dt / max(len(results), 1) * 1000:.0f} ms/file)\n')

    hdr = (f'{"Name":<44} {"SR":>6} {"Ch":>2} {"Len":>5} {"Flat":>5} '
           f'{"Tilt":>5} {"Low":>5} {"Mid":>5} {"High":>5} {"Air":>5}  Tags')
    print(hdr)
    print('-' * len(hdr))
    for r in sorted(results, key=lambda r: r.flatness_db)[:limit]:
        name = r.path.replace('\\', '/').split('/')[-1]
        b = r.band_levels
        print(f'{name[:44]:<44} {r.sample_rate:>6} {r.channels:>2} '
              f'{r.effective_length_ms:>5.0f} {r.flatness_db:>5.1f} '
              f'{r.tilt_db_oct:>5.1f} {b["Low"]:>5.1f} {b["Mid"]:>5.1f} '
              f'{b["High"]:>5.1f} {b["Air"]:>5.1f}  {",".join(r.tags)}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
