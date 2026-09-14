class UpstreamError(Exception):
    """Raised after retries are exhausted for one upstream call. Caught per-source in the
    ingestion runner so one dead upstream never takes down the others (hard rule 7)."""
