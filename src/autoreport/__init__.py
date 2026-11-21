"""Weekly business exports in, formatted report out, with a data-quality gate in between."""

from autoreport.config import Config, load_config
from autoreport.gate import Finding
from autoreport.pipeline import RunResult, run_period

__all__ = ["Config", "Finding", "RunResult", "load_config", "run_period"]
__version__ = "0.1.0"
