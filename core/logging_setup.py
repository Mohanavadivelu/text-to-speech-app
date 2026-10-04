"""Logging to the console and to logs/kokoro_tts.log (rotating)."""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from core import paths

_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s - %(message)s"
_QUIET = ("urllib3", "httpx", "httpcore", "huggingface_hub", "filelock", "PIL",
          "matplotlib", "numba", "phonemizer", "h5py")


def setup_logging(level=logging.INFO) -> str:
    """Configure logging once; returns the log file path."""
    paths.ensure_dirs()
    root = logging.getLogger()
    if getattr(root, "_kokoro_configured", False):
        return paths.LOG_PATH
    root.setLevel(level)
    fmt = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(paths.LOG_PATH, maxBytes=2_000_000, backupCount=5,
                                       encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if sys.stderr is not None:   # a --noconsole build has no stderr
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
        root.addHandler(console)

    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    _route_loguru()
    _install_excepthooks()
    root._kokoro_configured = True
    return paths.LOG_PATH


def _route_loguru():
    """kokoro/misaki log through loguru; send their warnings to our log too."""
    try:
        from loguru import logger as loguru_logger
    except ImportError:
        return
    std = logging.getLogger("kokoro")

    def _sink(message):
        record = message.record
        std.log(logging.WARNING if record["level"].no < 40 else logging.ERROR,
                record["message"])

    loguru_logger.remove()
    loguru_logger.add(_sink, level="WARNING")


def _install_excepthooks():
    log = logging.getLogger("crash")

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        log.critical("Uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _hook
    threading.excepthook = _thread_hook


def log_tk_exception(exc_type, exc, tb):
    """Use as Tk's report_callback_exception so UI errors reach the log file."""
    logging.getLogger("ui").error("Error in UI callback", exc_info=(exc_type, exc, tb))
