"""
Loader resiliente para VomoMLX.

Garante import de `mlx_vomo.py` mesmo quando o runtime (uvicorn/celery/scripts)
não inicia com a raiz do projeto no `sys.path`.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

_CACHED_VOMO_CLASS = None


def _iter_candidate_roots(caller_file: Optional[str] = None):
    seen: set[str] = set()

    def _yield_path(path: Path):
        key = str(path)
        if key not in seen:
            seen.add(key)
            yield path

    env_root = os.getenv("IUDEX_PROJECT_ROOT")
    if env_root:
        path = Path(env_root).expanduser().resolve()
        for candidate in _yield_path(path):
            yield candidate

    if caller_file:
        caller_path = Path(caller_file).resolve()
        for candidate in _yield_path(caller_path.parent):
            yield candidate
        for parent in caller_path.parents:
            for candidate in _yield_path(parent):
                yield candidate

    cwd = Path.cwd().resolve()
    for candidate in _yield_path(cwd):
        yield candidate
    for parent in cwd.parents:
        for candidate in _yield_path(parent):
            yield candidate

    this_file = Path(__file__).resolve()
    for parent in this_file.parents:
        for candidate in _yield_path(parent):
            yield candidate


def _find_mlx_vomo_file(caller_file: Optional[str] = None) -> Optional[Path]:
    for root in _iter_candidate_roots(caller_file=caller_file):
        candidate = root / "mlx_vomo.py"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_vomo_class(caller_file: Optional[str] = None):
    """
    Retorna a classe VomoMLX com fallback por caminho absoluto.
    """
    global _CACHED_VOMO_CLASS
    if _CACHED_VOMO_CLASS is not None:
        return _CACHED_VOMO_CLASS

    direct_error: Optional[Exception] = None
    try:
        from mlx_vomo import VomoMLX  # type: ignore

        _CACHED_VOMO_CLASS = VomoMLX
        return _CACHED_VOMO_CLASS
    except Exception as exc:
        direct_error = exc

    module_path = _find_mlx_vomo_file(caller_file=caller_file or __file__)
    if not module_path:
        raise ImportError("mlx_vomo.py não encontrado em nenhum caminho candidato") from direct_error

    module_root = module_path.parent
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

    import_error: Optional[Exception] = None
    try:
        module = importlib.import_module("mlx_vomo")
        vomo_class = getattr(module, "VomoMLX", None)
        if vomo_class is not None:
            _CACHED_VOMO_CLASS = vomo_class
            return _CACHED_VOMO_CLASS
    except Exception as exc:
        import_error = exc

    try:
        spec = importlib.util.spec_from_file_location("mlx_vomo", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Spec inválida para {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["mlx_vomo"] = module
        spec.loader.exec_module(module)
        vomo_class = getattr(module, "VomoMLX", None)
        if vomo_class is None:
            raise ImportError("Classe VomoMLX não encontrada em mlx_vomo.py")
        _CACHED_VOMO_CLASS = vomo_class
        return _CACHED_VOMO_CLASS
    except Exception as fallback_error:
        raise ImportError(
            "Falha ao importar VomoMLX: "
            f"direto={direct_error!r}; importlib={import_error!r}; fallback={fallback_error!r}"
        ) from fallback_error

