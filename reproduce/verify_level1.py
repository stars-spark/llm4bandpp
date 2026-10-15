#!/usr/bin/env python3
"""Level 1 check: regenerate every table and figure of the paper and the supplement and compare them with the paper's.

Runs the level-1 commands of docs/PACKAGE.md (tables, supplement tables, Figs. S1, 3 and 4, the observation grid of Fig. 1,
pdflatex on the TikZ sources of Figs. 1 and 2) and compares every output with the reference copy under expected/:
text files byte for byte, PDFs by rendering each page at 150 dpi with pdftoppm and comparing the pixels with Pillow.

By default the commands run in a temporary copy of the package, so the package itself stays as released; --in-place
runs them in the package. The path placeholders of docs/PACKAGE.md are set in whichever tree the commands run in; paths
already set for that tree are left as they are, paths set for another location (a moved package) are pointed at it.
Exit status: 0 when every output is identical to the reference or was skipped for a missing tool, 1 when an output
differs, is missing or a command fails, 2 on a usage error.

Usage, from the package root:  python3 reproduce/verify_level1.py [--in-place] [--workdir DIR] [--keep] [--dpi 150]
"""
import argparse, difflib, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PAPER = "papers/revision-v2"
PH_ROOT, PH_TB = "/path/to/llm4bandpp", "/path/to/testbed/results"
TB_REL = "external/testbed/results"
ANCHOR = "scripts/paper/steady_state_qoe_v1.py"   # holds ROOT = Path("...") and TB = Path("...") once the placeholders are set


def requirements_name(root=ROOT):
    """The file that pins the level-1 versions: requirements-level1.txt, or requirements.txt in packages without it."""
    for n in ("requirements-level1.txt", "requirements.txt"):
        if (root / n).is_file(): return n
    return "requirements-level1.txt"


# ---------------------------------------------------------------------------------------------------------------------
# Path placeholders and package copies (also used by reproduce/level2_checks.py)

def previous_paths(root):
    """Package root and testbed results path that an earlier substitution wrote into the scripts, or None."""
    p = root / ANCHOR
    if not p.is_file(): return None, None
    t = p.read_text(encoding="utf-8", errors="replace")
    r = re.search(r'ROOT = Path\("([^"]*)"\)', t); b = re.search(r'TB = Path\("([^"]*)"\)', t)
    r = r.group(1) if r and r.group(1) != PH_ROOT else None
    b = b.group(1) if b and b.group(1) != PH_TB else None
    return r, b


def replacement_pairs(root, repoint=True, own_testbed=True):
    """(old, new) byte pairs that set the path placeholders for a tree at root.

    With repoint, a package root that an earlier substitution wrote into the scripts (the package was moved, or this is
    a copy of a package whose placeholders were set) is replaced by root. With own_testbed, a testbed results path set
    earlier is replaced by the package's copy in external/testbed/results, as the placeholder substitution of docs/PACKAGE.md sets it."""
    root = Path(root).resolve(); tb = str(root / TB_REL)
    pairs = [(PH_TB, tb), (PH_ROOT, str(root))]
    if repoint:
        old_root, old_tb = previous_paths(root)
        if own_testbed and old_tb and old_tb != tb: pairs.append((old_tb, tb))
        if old_root and old_root != str(root): pairs.append((old_root, str(root)))
    return [(a.encode(), b.encode()) for a, b in pairs]


def apply_pairs(data, pairs):
    for a, b in pairs: data = data.replace(a, b)
    return data


def set_placeholders(root, repoint=True, own_testbed=True):
    """The placeholder substitution of docs/PACKAGE.md in Python: every file under scripts/ and papers/ that holds a placeholder. Idempotent.

    Returns the number of files changed."""
    root = Path(root).resolve(); pairs = replacement_pairs(root, repoint, own_testbed); n = 0
    for top in ("scripts", "papers"):
        for dp, dn, fn in os.walk(root / top):
            dn[:] = [d for d in dn if d != "__pycache__"]
            for f in fn:
                p = Path(dp) / f
                if p.is_symlink() or not p.is_file(): continue
                b = p.read_bytes()
                if not any(a in b for a, _ in pairs): continue
                nb = apply_pairs(b, pairs)
                if nb != b: p.write_bytes(nb); n += 1
    return n


def copy_package(src, dst):
    """Copy the package to dst (which must not exist), keeping time stamps; the reference outputs in expected/ stay behind."""
    src = Path(src).resolve()

    def skip(d, names):
        return [n for n in names if n == "__pycache__" or (n == "expected" and Path(d).resolve() == src)]
    shutil.copytree(src, dst, symlinks=True, ignore=skip)
    return Path(dst)


def tool_versions(req):
    """Installed against pinned versions of the packages in the requirements file, as printable lines."""
    from importlib import metadata
    out, differ = [f"python {sys.version.split()[0]} ({sys.executable})"], False
    if req.is_file():
        for ln in req.read_text().split("\n"):
            m = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s#]+)", ln)
            if not m: continue
            name, want = m.groups()
            try: have = metadata.version(name)
            except metadata.PackageNotFoundError: have = "not installed"
            ok = have.split("+")[0] == want
            differ |= not ok and name.lower() in ("numpy", "matplotlib", "pillow", "scipy")
            out.append(f"{name} {have}" + ("" if ok else f" (pinned {want})"))
    return out, differ


# ---------------------------------------------------------------------------------------------------------------------
# Level-1 commands and outputs

def steps(root, py):
    """(key, command as in docs/PACKAGE.md, argv, cwd, extra environment, tool it needs)."""
    src = root / PAPER / "figs/src"
    return [
        ("tables", "python3 scripts/paper/make_tables_v2.py", [py, "scripts/paper/make_tables_v2.py"], root, {}, None),
        ("supp", "python3 papers/revision-v2/supplement/make_supp_tables.py", [py, f"{PAPER}/supplement/make_supp_tables.py"], root, {}, None),
        ("figS1", "python3 scripts/paper/make_fig_lambda_supp_v2.py", [py, "scripts/paper/make_fig_lambda_supp_v2.py"], root, {}, None),
        ("fig3", "FIG_OUT=$PWD/papers/revision-v2/figs/fig_designer_three.pdf python3 scripts/paper/make_fig_designer_v6.py",
         [py, "scripts/paper/make_fig_designer_v6.py"], root, {"FIG_OUT": str(root / PAPER / "figs/fig_designer_three.pdf")}, "pdflatex"),
        ("fig4", "python3 scripts/paper/make_fig_closedloop_v1.py", [py, "scripts/paper/make_fig_closedloop_v1.py"], root, {}, None),
        ("grid", "python3 scripts/paper/make_fig1_collector_grid_v1.py --palette greys --lighten 0.4 --out papers/revision-v2/figs/src/collector_grid_greys_light.tex",
         [py, "scripts/paper/make_fig1_collector_grid_v1.py", "--palette", "greys", "--lighten", "0.4", "--out", f"{PAPER}/figs/src/collector_grid_greys_light.tex"], root, {}, None),
        ("fig1", "(cd papers/revision-v2/figs/src && pdflatex fig_llm_position.tex)",
         ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "fig_llm_position.tex"], src, {}, "pdflatex"),
        ("fig2", "(cd papers/revision-v2/figs/src && pdflatex fig_envelope.tex)",
         ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "fig_envelope.tex"], src, {}, "pdflatex"),
    ]


# (output in the package relative to papers/revision-v2, reference under expected/, paper element, step that writes it)
OUTPUTS = [
    ("tables/table_offline.tex", "tables/table_offline.tex", "Table I", "tables"),
    ("tables/table_position.tex", "tables/table_position.tex", "Table II", "tables"),
    ("tables/table_cost.tex", "tables/table_cost.tex", "Table III", "tables"),
    ("tables/table_designer.tex", "tables/table_designer.tex", "Table IV", "tables"),
    ("tables/table_closedloop_v2.tex", "tables/table_closedloop_v2.tex", "Table V", "tables"),
    ("tables/table_closedloop.tex", "tables/table_closedloop.tex", "Sec. V-F (after-30-s, SSIM and freeze columns; not in the paper)", "tables"),
    ("supplement/generated/tab_variants.tex", "supplement/generated/tab_variants.tex", "Table S3", "supp"),
    ("supplement/generated/tab_eplus.tex", "supplement/generated/tab_eplus.tex", "Table S4", "supp"),
    ("supplement/generated/tab_designer_src.tex", "supplement/generated/tab_designer_src.tex", "Sec. S8 per-stack table (released with the code)", "supp"),
    ("supplement/generated/prompt_template.txt", "supplement/generated/prompt_template.txt", "Fig. S2 (prompt)", "supp"),
    ("supplement/figS_lambda.pdf", "supplement/figS_lambda.pdf", "Fig. S1", "figS1"),
    ("figs/fig_designer_three.pdf", "figs/fig_designer_three.pdf", "Fig. 3", "fig3"),
    ("figs/fig_closedloop_dynamics.pdf", "figs/fig_closedloop_dynamics.pdf", "Fig. 4", "fig4"),
    ("figs/src/collector_grid_greys_light.tex", "figs/src/collector_grid_greys_light.tex", "Fig. 1 (observation grid)", "grid"),
    ("figs/src/fig_llm_position.pdf", "figs/fig_llm_position.pdf", "Fig. 1", "fig1"),
    ("figs/src/fig_envelope.pdf", "figs/fig_envelope.pdf", "Fig. 2", "fig2"),
]


def stat_key(p):
    try: s = p.stat(); return (s.st_size, s.st_mtime_ns, s.st_ino)
    except FileNotFoundError: return None


# ---------------------------------------------------------------------------------------------------------------------
# Comparison

def compare_text(new, ref, logdir):
    a, b = ref.read_bytes(), new.read_bytes()
    if a == b: return True, "identical"
    la = a.decode("utf-8", "replace").splitlines(keepends=True); lb = b.decode("utf-8", "replace").splitlines(keepends=True)
    diff = list(difflib.unified_diff(la, lb, f"expected/{ref.name}", f"output/{new.name}"))
    n = sum(1 for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---")))
    (logdir / f"{new.name}.diff").write_text("".join(diff), encoding="utf-8")
    return False, f"differs ({n} lines)"


def changed_pixels(a, b):
    from PIL import Image, ImageChops
    A, B = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if A.size != B.size: return None, f"{B.size[0]}x{B.size[1]} pixels, reference {A.size[0]}x{A.size[1]}"
    d = ImageChops.difference(A, B)
    if d.getbbox() is None: return 0, ""
    bands = [x.point(lambda v: 255 if v else 0) for x in d.split()]
    m = bands[0]
    for x in bands[1:]: m = ImageChops.lighter(m, x)
    return m.histogram()[255], ""


def compare_pdf(new, ref, render_dir, dpi, tag):
    out = render_dir / tag; out.mkdir(parents=True, exist_ok=True)
    pages = {}
    for side, pdf in (("ref", ref), ("new", new)):
        r = subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(out / side)], capture_output=True, text=True)
        if r.returncode: return False, f"differs (pdftoppm failed on the {'reference' if side == 'ref' else 'output'})"
        pages[side] = sorted(out.glob(f"{side}-*.png"))
    if len(pages["ref"]) != len(pages["new"]): return False, f"differs ({len(pages['new'])} pages vs {len(pages['ref'])})"
    total = 0
    for i, (a, b) in enumerate(zip(pages["ref"], pages["new"]), 1):
        n, why = changed_pixels(a, b)
        if n is None: return False, f"differs (page {i}: {why})"
        total += n
    return (True, "identical") if total == 0 else (False, f"differs ({total} pixels)")


def print_table(head, rows):
    w = [max(len(str(r[i])) for r in [head] + rows) for i in range(len(head))]
    line = lambda r: " | ".join(str(c).ljust(w[i]) for i, c in enumerate(r)).rstrip()
    print(line(head)); print("-+-".join("-" * x for x in w))
    for r in rows: print(line(r))


# ---------------------------------------------------------------------------------------------------------------------

def main():
    req = requirements_name()
    ap = argparse.ArgumentParser(
        prog="python3 reproduce/verify_level1.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Regenerate every table and figure of the paper and the supplement (docs/PACKAGE.md, level 1) and compare "
                    "them with the reference outputs in expected/: text byte for byte, PDFs pixel by pixel at 150 dpi.",
        epilog=f"Pixel identity of the figures needs the pinned versions of {req} (Python 3.13, numpy, matplotlib, "
               "scipy and Pillow as listed there) and TeX Live with pdflatex, helvet, sansmath and TikZ; poppler's "
               "pdftoppm renders the PDFs. With other versions the tables stay byte-identical but figures can differ in "
               "a few pixels, and Fig. 3 may fail (it needs matplotlib 3.11). Run from the package root.")
    ap.add_argument("--in-place", action="store_true", help="run in the package itself instead of a temporary copy")
    ap.add_argument("--workdir", help="directory for the temporary copy, renders and logs (default: the system temporary directory)")
    ap.add_argument("--keep", action="store_true", help="keep the copy, renders and logs (they are kept anyway when a check fails)")
    ap.add_argument("--dpi", type=int, default=150, help="render resolution for the PDF comparison (default 150)")
    A = ap.parse_args()

    ref_dir = ROOT / "expected"
    if A.workdir: Path(A.workdir).mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="llm4bandpp-level1-", dir=A.workdir))
    logdir, render_dir = base / "logs", base / "render"; logdir.mkdir(); render_dir.mkdir()
    print(f"package: {ROOT}")
    old_root, old_tb = previous_paths(ROOT)
    if old_root and old_root != str(ROOT): print(f"note: the scripts pointed at {old_root}; pointing them at the working tree")
    if old_tb and old_tb != str(ROOT / TB_REL) and not (old_root and old_tb == f"{old_root}/{TB_REL}"):
        print(f"note: the testbed results path was set to {old_tb}; "
              + ("kept (in place)" if A.in_place else f"the copy reads the package's {TB_REL}/ instead"))
    if A.in_place:
        work = ROOT
        n = set_placeholders(work, own_testbed=False)
    else:
        work = copy_package(ROOT, base / "llm4bandpp")
        n = set_placeholders(work)
    print(f"working tree: {work}" + (" (copy)" if not A.in_place else " (in place)") + f"; placeholders set in {n} files")
    vers, vdiff = tool_versions(ROOT / req)
    print("versions: " + "; ".join(vers))
    if vdiff: print(f"note: versions differ from {req}; figures may differ in a few pixels")

    py = sys.executable
    have = {"pdflatex": shutil.which("pdflatex"), "pdftoppm": shutil.which("pdftoppm")}
    try: import PIL   # noqa: F401
    except ImportError: have["Pillow"] = None
    else: have["Pillow"] = True
    if have["pdflatex"]:
        v = subprocess.run(["pdflatex", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
        print(f"pdflatex: {v}")

    before = {o: stat_key(work / PAPER / o) for o, _, _, _ in OUTPUTS}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    run_rows, status = [], {}
    for key, shown, argv, cwd, extra, tool in steps(work, py):
        if tool and not have.get(tool):
            status[key] = f"skipped: {tool} not found"; run_rows.append((shown, "skipped", "-")); continue
        t0 = time.time()
        with open(logdir / f"{key}.log", "w", encoding="utf-8") as log:
            r = subprocess.run(argv, cwd=cwd, env=dict(env, **extra), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        dt = time.time() - t0
        status[key] = "ok" if r.returncode == 0 else f"exit {r.returncode}"
        run_rows.append((shown, r.returncode, f"{dt:.1f}"))
    print()
    print_table(("Command", "Exit", "Seconds"), run_rows)

    listed = None
    ef = Path(__file__).with_name("EXPECTED_FILES.txt")
    if ef.is_file(): listed = {l.strip() for l in ef.read_text().split("\n") if l.strip() and not l.startswith("#")}

    rows, bad, skipped = [], 0, 0
    for out_rel, ref_rel, element, key in OUTPUTS:
        new, ref = work / PAPER / out_rel, ref_dir / ref_rel
        shown = f"{PAPER}/{out_rel}"
        st = status.get(key, "")
        if st.startswith("skipped"):
            rows.append((shown, element, st)); skipped += 1; continue
        if not ref.is_file():
            rows.append((shown, element, f"no reference (expected/{ref_rel} missing)")); bad += 1; continue
        if not new.is_file():
            rows.append((shown, element, "missing" + ("" if st == "ok" else f" (command {st})"))); bad += 1; continue
        if stat_key(new) == before[out_rel]:
            rows.append((shown, element, "missing (not regenerated" + ("" if st == "ok" else f", command {st}") + ")")); bad += 1; continue
        if new.suffix == ".pdf":
            if not have["pdftoppm"]: rows.append((shown, element, "skipped: pdftoppm not found")); skipped += 1; continue
            if not have["Pillow"]: rows.append((shown, element, "skipped: Pillow not installed")); skipped += 1; continue
            ok, msg = compare_pdf(new, ref, render_dir, A.dpi, Path(out_rel).stem)
        else:
            ok, msg = compare_text(new, ref, logdir)
        rows.append((shown, element, msg)); bad += not ok
    print()
    print_table(("Output", "Paper element", "Result"), rows)
    if listed is not None:
        miss = sorted({r for _, r, _, _ in OUTPUTS} - listed)
        if miss: print(f"note: not listed in reproduce/EXPECTED_FILES.txt: {', '.join(miss)}")
    failed = [s for s in status.values() if s.startswith("exit")]
    ident = sum(1 for r in rows if r[2] == "identical")
    print(f"\n{ident} of {len(rows)} outputs identical to the paper, {bad} not, {skipped} skipped; "
          f"{len(failed)} of {len(status)} commands failed")
    if bad or failed or A.keep:
        print(f"{'logs and renders' if A.in_place else 'copy, logs and renders'} kept in {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    sys.exit(1 if bad or failed else 0)


if __name__ == "__main__":
    main()
