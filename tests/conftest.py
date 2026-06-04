from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_app_package() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_root = repo_root / 'app'
    init_file = package_root / '__init__.py'

    if 'app' in sys.modules and getattr(sys.modules['app'], '__path__', None):
        return

    spec = importlib.util.spec_from_file_location(
        'app',
        init_file,
        submodule_search_locations=[str(package_root)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError('无法加载 app 包')

    module = importlib.util.module_from_spec(spec)
    sys.modules['app'] = module
    spec.loader.exec_module(module)


_load_app_package()
