#!/usr/bin/env bash
# make_hd720_sources_v1.sh (2026-10-03): the 720p sources of hd720-closedloop-v1 and compete-flow-v1.
# download: fetch the five 720p source sequences from Xiph into the staging directory, check their sizes, record the upstream
#   sha256 and ffprobe output; Johnny, Mobcal and Parkrun are compared with the upstream hashes already recorded in
#   testmedia/paper_720p_provenance.json (Johnny must match, otherwise stop).
# make LAYOUT: first 10 s; 60 fps sequences keep every other frame (select even frames), 50 fps sequences are resampled with
#   fps=30, giving 300 frames at 30 fps; a black label band is drawn at the bottom with a 6-digit frame number (from 1) in
#   DejaVuSansMono-Bold; raw yuv420p goes to the shared testmedia directory with a provenance record and sha256.
#   Layout b144 (used): the band is the bottom 144 rows (from row 576), font size 112, evaluated region the top 576 rows.
#   Layout third: the relative layout of the 320x240 sources, band the bottom third (from row 480), font size 156, number
#   30 rows below the band top (fallback if the OCR check fails).
# cleanup: after the sources pass their checks, delete the downloaded upstream files (public files whose hashes and ffprobe
#   output are recorded) to free disk space.
set -euo pipefail
STAGE=/path/to/testbed/hd720_staging
TM=/path/to/alphartc/LLM4Band/testmedia
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf
JOHNNY_SHA=412eef72f06e22bad30cccc527eddc3ae1cb98f3c145472f13f30844520b2517
ids=(johnny fourpeople kristenandsara mobcal parkrun)
files=(Johnny_1280x720_60.y4m FourPeople_1280x720_60.y4m KristenAndSara_1280x720_60.y4m 720p50_mobcal_ter.y4m 720p50_parkrun_ter.y4m)
sizes=(830826065 830826065 830826065 696732659 696732659)
fpss=(60 60 60 50 50)
cmd=${1:?Usage: make_hd720_sources_v1.sh download|make layout|cleanup}
mkdir -p "$STAGE"

fetch() {
  python3 - "$1" "$2" "$3" <<'PYFETCH'
import os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
url, out, size = sys.argv[1], sys.argv[2], int(sys.argv[3]); CH = 8 << 20
if os.path.exists(out) and os.path.getsize(out) == size: sys.exit(0)
parts = [(i, i * CH, min(size, (i + 1) * CH) - 1) for i in range((size + CH - 1) // CH)]
def get(p):
    i, a, b = p; f = f"{out}.c{i:04d}"
    if os.path.exists(f) and os.path.getsize(f) == b - a + 1: return True
    for _ in range(12):
        r = subprocess.run(["curl", "-L", "--fail", "-s", "--speed-limit", "100000", "--speed-time", "10", "--max-time", "300", "-r", f"{a}-{b}", "-o", f + ".tmp", url])
        if r.returncode == 0 and os.path.getsize(f + ".tmp") == b - a + 1: os.replace(f + ".tmp", f); return True
    return False
with ThreadPoolExecutor(12) as ex: ok = list(ex.map(get, parts))
if not all(ok): print(f"{out} has blocks not fully downloaded", file=sys.stderr); sys.exit(1)
with open(out, "wb") as h:
    for i, a, b in parts:
        with open(f"{out}.c{i:04d}", "rb") as c: h.write(c.read())
for i, a, b in parts: os.remove(f"{out}.c{i:04d}")
PYFETCH
}

if [[ "$cmd" == download ]]; then
  curl -L --fail --retry 5 --retry-delay 20 -s https://media.xiph.org/video/derf/ -o "$STAGE/xiph_derf_index_20261003.html"
  for i in 0 1 2 3 4; do
    id=${ids[$i]}; f=${files[$i]}; out="$STAGE/$id.y4m"
    fetch "https://media.xiph.org/video/derf/y4m/$f" "$out" "${sizes[$i]}"
    got=$(stat -c %s "$out"); [[ "$got" == "${sizes[$i]}" ]] || { echo "$id size $got not equal to ${sizes[$i]}" >&2; exit 32; }
    sha256sum "$out" | awk -v n="$f" '{print $1"  "n}' > "$STAGE/${id}_upstream.sha256"
    ffprobe -v error -show_streams -show_format -of json "$out" > "$STAGE/${id}_ffprobe.json"
    echo "Download complete $id $(cut -c1-16 "$STAGE/${id}_upstream.sha256")"
  done
  h=$(cut -d' ' -f1 "$STAGE/johnny_upstream.sha256")
  [[ "$h" == "$JOHNNY_SHA" ]] || { echo "Johnny upstream hash $h does not match the recorded $JOHNNY_SHA" >&2; exit 33; }
  date -Is > "$STAGE/DOWNLOAD_COMPLETE"; echo "Johnny upstream hash matches the recorded one"; exit 0
fi

if [[ "$cmd" == make ]]; then
  layout=${2:?Missing layout b144 or third}
  case "$layout" in
    b144) label_y=576; font=112; ytext="576+(144-th)/2" ;;
    third) label_y=480; font=156; ytext="510" ;;
    *) echo "Unknown layout $layout" >&2; exit 2 ;;
  esac
  [[ -f "$STAGE/DOWNLOAD_COMPLETE" ]] || { echo "download first" >&2; exit 2; }
  for i in 0 1 2 3 4; do
    id=${ids[$i]}; src="$STAGE/$id.y4m"; out="$TM/hd720_${id}_30f300_${layout}.yuv"
    if [[ "${fpss[$i]}" == 60 ]]; then pre="select=not(mod(n\\,2)),setpts=N/(30*TB)"; else pre="fps=30"; fi
    vf="$pre,drawbox=x=0:y=$label_y:w=iw:h=ih-$label_y:color=black@1:t=fill,drawtext=fontfile=$FONT:text='%{eif\\:n+1\\:d\\:6}':fontcolor=white:fontsize=$font:x=(w-text_w)/2:y=$ytext"
    ffmpeg -hide_banner -nostdin -v error -y -i "$src" -t 10 -vf "$vf" -fps_mode passthrough -frames:v 300 -pix_fmt yuv420p -f rawvideo "$out"
    want=$((1280 * 720 * 3 / 2 * 300)); got=$(stat -c %s "$out")
    [[ "$got" == "$want" ]] || { echo "$id output $got bytes, expected $want" >&2; exit 34; }
    printf '%s\n' "$vf" > "$STAGE/${id}_${layout}_filter.txt"
    echo "Generate $out"
  done
  python3 - "$STAGE" "$TM" "$layout" "$label_y" "$font" "$JOHNNY_SHA" <<'PY'
import datetime, hashlib, json, sys
from pathlib import Path
st, tm, layout, label_y, font, jsha = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 23), b""): h.update(b)
    return h.hexdigest()
old = {v["candidate_id"]: v["source_sha256"] for v in json.load(open(tm / "paper_720p_provenance.json"))["videos"]}
ids = ["johnny", "fourpeople", "kristenandsara", "mobcal", "parkrun"]
names = {"johnny": "Johnny_1280x720_60.y4m", "fourpeople": "FourPeople_1280x720_60.y4m", "kristenandsara": "KristenAndSara_1280x720_60.y4m", "mobcal": "720p50_mobcal_ter.y4m", "parkrun": "720p50_parkrun_ter.y4m"}
role = {"johnny": "main batch", "fourpeople": "main batch", "kristenandsara": "Backup (scheme 2.2 replacement rule) and competitor material for competing call G2", "mobcal": "Only do upper-bound calibration", "parkrun": "Only do upper-bound calibration"}
vids = []
for i in ids:
    up = (st / f"{i}_upstream.sha256").read_text().split()[0]; out = tm / f"hd720_{i}_30f300_{layout}.yuv"
    ff = json.load(open(st / f"{i}_ffprobe.json")); vs = [s for s in ff["streams"] if s.get("codec_type") == "video"][0]
    vids.append({"id": i, "role": role[i], "upstream_url": "https://media.xiph.org/video/derf/y4m/" + names[i], "upstream_bytes": int(ff["format"]["size"]), "upstream_sha256": up,
                 "upstream_sha256_matches_paper_720p_provenance": (old.get(i) == up) if i in old else None, "upstream_r_frame_rate": vs.get("r_frame_rate"), "upstream_nb_frames": vs.get("nb_frames"),
                 "upstream_ffprobe": json.dumps({"width": vs.get("width"), "height": vs.get("height"), "pix_fmt": vs.get("pix_fmt"), "r_frame_rate": vs.get("r_frame_rate"), "duration": ff["format"].get("duration")}),
                 "filter": (st / f"{i}_{layout}_filter.txt").read_text().strip(), "output": str(out), "output_bytes": out.stat().st_size, "output_sha256": sha(out)})
assert vids[0]["upstream_sha256"] == jsha
prov = {"schema": "hd720-sources-v1", "created_beijing": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%F %T"), "layout": layout,
        "format": {"width": 1280, "height": 720, "fps": 30, "frames": 300, "seconds": 10, "pixel_format": "yuv420p8", "label_band_start_row": label_y, "label_font_px": font,
                   "eval_region_rows": label_y, "label": "6-digit frame number, starting from 1, DejaVuSansMono-Bold, white text on black band"},
        "preprocessing": "First 10 seconds; for the 60-frame sequence take even frames (select not(mod(n,2))), for the 50-frame sequence fps=30; then draw the label band and frame number; output headless yuv420p",
        "license_evidence": "Xiph Derf index page (saved at download time as staging/xiph_derf_index_20261003.html) and testmedia/ReadMe_720p.txt", "videos": vids}
(tm / f"hd720_sources_{layout}_provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1) + "\n")
with open(tm / f"hd720_sources_{layout}_sha256sums.txt", "w") as f:
    for v in vids: f.write(f"{v['output_sha256']}  {Path(v['output']).name}\n")
print(json.dumps([(v["id"], v["upstream_sha256"][:12], v["upstream_sha256_matches_paper_720p_provenance"], v["output_sha256"][:12]) for v in vids], ensure_ascii=False))
PY
  cp "$STAGE/xiph_derf_index_20261003.html" "$TM/hd720_xiph_derf_index_20261003.html"
  for i in 0 1 2 3 4; do cp "$STAGE/${ids[$i]}_upstream.sha256" "$TM/hd720_${ids[$i]}_upstream.sha256"; cp "$STAGE/${ids[$i]}_ffprobe.json" "$TM/hd720_${ids[$i]}_upstream_ffprobe.json"; done
  date -Is > "$TM/HD720_SOURCES_${layout}_COMPLETE"; exit 0
fi

if [[ "$cmd" == cleanup ]]; then
  for id in "${ids[@]}"; do rm -f "$STAGE/$id.y4m"; done; echo "Upstream original files deleted (hashes and ffprobe recorded in testmedia)"; exit 0
fi
echo "Unknown subcommand $cmd" >&2; exit 2
