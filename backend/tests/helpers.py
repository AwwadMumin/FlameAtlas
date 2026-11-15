"""Expected data-set sizes, computed from the data files (base inputs + extra sources) instead of hard-coded."""
from app.core.config import get_settings
from app.services.extra_sources import expected_counts

EXPECTED = expected_counts(get_settings().data_dir)
