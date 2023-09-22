"""Directory of all supported municipality websites that are hosted by itron."""

# Import all modules in the current directory.
from importlib import import_module
from pathlib import Path

from .base import MunicipalityBase

__all__ = ["MunicipalityBase"]

for f in Path(__file__).parent.glob("*.py"):
    module_name = f.stem
    if (not module_name.startswith("_")) and (module_name not in globals()):
        import_module(f".{module_name}", __package__)
    del f, module_name
del import_module, Path
