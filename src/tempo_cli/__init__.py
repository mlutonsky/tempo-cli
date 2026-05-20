from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("tempo-cli")
except PackageNotFoundError:  # editable install from source tree without metadata
    __version__ = "0.0.0+local"
