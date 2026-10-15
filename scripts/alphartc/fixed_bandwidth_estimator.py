"""Fixed-rate estimator: ignores packet reports and returns BWE_FIXED_BPS at every request."""

import os


class FixedBandwidthEstimator:
    """Ignore packet feedback and return the configured bitrate."""

    def __init__(self, bandwidth_bps=None):
        if bandwidth_bps is None:
            bandwidth_bps = int(os.environ.get("BWE_FIXED_BPS", "240000"))
        self.bandwidth_bps = int(bandwidth_bps)
        if self.bandwidth_bps <= 0:
            raise ValueError("fixed bandwidth must be positive")

    def report_states(self, stats):
        return None

    def get_estimated_bandwidth(self):
        return self.bandwidth_bps
