"""Azure SLO Guardian - Azure-native SLO/SLI engine."""

__version__ = "0.1.0"
__author__ = "Azure SLO Guardian Contributors"
__license__ = "MIT"

from azure_slo_guardian.config import SLOConfig, load_config
from azure_slo_guardian.slo_calculator import SLOCalculator, ErrorBudget

__all__ = ["SLOConfig", "load_config", "SLOCalculator", "ErrorBudget", "__version__"]
