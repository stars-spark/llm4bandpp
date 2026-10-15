#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send a directory of frozen prompts to the DeepSeek chat API and store one JSON reply per prompt and sample.
Prompt hashes are checked against SHA256SUMS.json before any request; samples that already have an output file are skipped.
Requests go out only off-peak (is_peak, with a SAFETY_MIN margin before peak hours); the run stops if the account balance check falls below MIN_BALANCE.
No temperature is set (model default) and max_tokens is 64000. A reply cut at the length limit is logged under _truncated/ and retried once, then kept as is.
Usage: python api_runner_v1.py --model deepseek-flash --arm NAME --prompts DIR --out DIR [--samples 3] [--sample-index k] [--selftest]
"""
import argparse, datetime as dt, hashlib, json, sys, time, urllib.request
from pathlib import Path
KEY = Path.home() / ".config/deepseek/api_key"; MIN_BALANCE, SAFETY_MIN = 5.0, 20
HOLIDAYS = {dt.date(2026, 10, d) for d in range(1, 8)}


def is_peak(t):
    """Return True if UTC time t falls in the provider's weekday peak hours (01:00-04:00 or 06:00-10:00 UTC), listed holidays excluded."""
    bj = (t + dt.timedelta(hours=8)).date()
    return t.weekday() < 5 and bj not in HOLIDAYS and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def ok_to_send(now=None):
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return not is_peak(now) and not is_peak(now + dt.timedelta(minutes=SAFETY_MIN))


def selftest():
    D = dt.datetime
    assert is_peak(D(2026, 9, 29, 2, 0)) and is_peak(D(2026, 9, 29, 7, 30))
    assert not is_peak(D(2026, 9, 29, 4, 30)) and not is_peak(D(2026, 9, 28, 11, 30))
    assert not is_peak(D(2026, 10, 3, 2, 0)) and not is_peak(D(2026, 10, 2, 7, 0))
    assert not ok_to_send(D(2026, 9, 29, 0, 45)) and ok_to_send(D(2026, 9, 29, 0, 30))
    print("Off-peak check self-test passed")


def balance(key):
    r = json.load(urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"}), timeout=60))
    return float(r["balance_infos"][0]["total_balance"])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--arm", required=True); ap.add_argument("--prompts", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=3); ap.add_argument("--sample-index", type=int, default=None); ap.add_argument("--selftest", action="store_true"); a = ap.parse_args()
    selftest()
    if a.selftest: return
    P = Path(a.prompts); man = json.load(open(P / "SHA256SUMS.json"))
    for n, h in man.items(): assert hashlib.sha256((P / f"{n}.txt").read_text().encode()).hexdigest() == h, f"{n} prompt hash does not match"
    key = KEY.read_text().strip(); out = Path(a.out) / a.arm; out.mkdir(parents=True, exist_ok=True); tr = Path(a.out) / "_truncated" / a.arm
    for name in man:
        for s in (range(a.samples) if a.sample_index is None else [a.sample_index]):
            f = out / f"{name}.s{s}.json"
            if f.exists(): continue
            while not ok_to_send(): print(time.strftime("%F %T"), "peak hours, waiting", flush=True); time.sleep(600)
            b = balance(key)
            if b < MIN_BALANCE:
                (Path(a.out) / f"STOPPED_BALANCE_{a.arm}").write_text(f"{time.strftime('%F %T')} balance {b}"); print("balance below MIN_BALANCE, stopping", b, flush=True); sys.exit(3)
            body = json.dumps({"model": a.model, "messages": [{"role": "user", "content": (P / f"{name}.txt").read_text()}], "max_tokens": 64000}).encode()
            for trunc_try in range(2):
                for attempt in range(4):
                    try:
                        req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
                        r = json.load(urllib.request.urlopen(req, timeout=1800)); break
                    except Exception as e:
                        print("Retry", name, s, type(e).__name__, str(e)[:100], flush=True); time.sleep(30 * (attempt + 1))
                else:
                    raise SystemExit(f"{name} sampling attempt {s} failed")
                ch = r["choices"][0]; truncated = ch.get("finish_reason") == "length" or not (ch["message"].get("content") or "").strip()
                if not truncated or trunc_try == 1: break
                tr.mkdir(parents=True, exist_ok=True); (tr / f"{name}.s{s}.json").write_text(json.dumps({"usage": r.get("usage"), "finish_reason": ch.get("finish_reason")}))
            f.write_text(json.dumps({"model": a.model, "returned_model": r.get("model"), "time": time.strftime("%F %T"), "utc": dt.datetime.utcnow().isoformat(), "prompt_sha256": man[name],
                                     "content": ch["message"].get("content") or "", "finish_reason": ch.get("finish_reason"), "usage": r.get("usage")}, ensure_ascii=False))
            print(time.strftime("%F %T"), a.arm, name, s, r.get("usage", {}).get("completion_tokens"), "balance", b, flush=True)
    (out / (f"DONE_s{a.sample_index}" if a.sample_index is not None else "DONE")).write_text(time.strftime("%F %T"))


if __name__ == "__main__":
    main()
