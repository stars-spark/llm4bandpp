"""AlphaRTC Python estimator bridge copied from the configured receiver runtime."""
import json
import sys


def find_estimator_class():
    import BandwidthEstimator
    return BandwidthEstimator.Estimator


def main(ifd=sys.stdin, ofd=sys.stdout):
    estimator = find_estimator_class()()
    while True:
        line = ifd.readline()
        if not line:
            break
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        stripped = line.strip()
        try:
            stats = json.loads(stripped)
        except (TypeError, ValueError):
            stats = None
        if isinstance(stats, dict):
            estimator.report_states(stats)
        elif stripped == "RequestBandwidth":
            bandwidth = estimator.get_estimated_bandwidth()
            value = ("%d\n" % int(bandwidth)).encode("utf-8")
            try:
                ofd.write(value)
            except TypeError:
                ofd.write(value.decode("utf-8"))
            ofd.flush()
        else:
            try:
                ofd.write(line)
                ofd.flush()
            except TypeError:
                ofd.write(line.encode("utf-8"))
                ofd.flush()


if __name__ == "__main__":
    main()
