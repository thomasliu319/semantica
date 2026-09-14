import json
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/Users/thomasliu/myspace/semantica/.mplconfig")
os.environ.setdefault("NUMBA_CACHE_DIR", "/Users/thomasliu/myspace/semantica/.numba_cache")
os.environ["BROWSER"] = "echo"

ROOT = Path("/Users/thomasliu/myspace/semantica")
OUT = ROOT / ".cookbook_test_out"
OUT.mkdir(exist_ok=True)
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

NOTEBOOKS = [
    ROOT / "cookbook/introduction/16_Visualization.ipynb",
    ROOT / "cookbook/advanced/03_Complete_Visualization_Suite.ipynb",
]

saved_figs = []
try:
    import plotly.graph_objects as go

    def _show(self, *args, **kwargs):
        path = OUT / f"fig_{len(saved_figs)+1:02d}.html"
        self.write_html(str(path), include_plotlyjs="cdn")
        saved_figs.append(str(path))
        print(f"[saved] {path}")
        return self

    go.Figure.show = _show
except Exception as e:
    print("plotly patch skipped:", e)

results = []
for nb_path in NOTEBOOKS:
    print("\n" + "=" * 72)
    print(f"NOTEBOOK: {nb_path.relative_to(ROOT)}")
    print("=" * 72)
    nb = json.loads(nb_path.read_text())
    ns = {"__name__": "__main__"}
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        stripped = src.strip()
        if not stripped:
            continue
        if stripped.startswith("!") or stripped.startswith("%"):
            print(f"\n[skip cell {i}] {stripped.splitlines()[0][:80]}")
            results.append((nb_path.name, i, "skipped", stripped.splitlines()[0][:80]))
            continue
        print(f"\n--- {nb_path.name} cell {i} ---")
        try:
            exec(compile(src, f"{nb_path.name}:cell{i}", "exec"), ns, ns)
            for key in (
                "visualization",
                "dashboard",
                "animation",
                "timeline",
                "fig",
                "centrality_fig",
                "community_fig",
            ):
                obj = ns.get(key)
                if obj is not None and hasattr(obj, "write_html"):
                    path = OUT / f"{nb_path.stem}_{key}_cell{i}.html"
                    obj.write_html(str(path), include_plotlyjs="cdn")
                    saved_figs.append(str(path))
                    print(f"[saved] {path}")
            results.append((nb_path.name, i, "ok", ""))
            print(f"[ok] cell {i}")
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"[FAIL] cell {i}: {err}")
            traceback.print_exc()
            results.append((nb_path.name, i, "fail", err))

print("\nSUMMARY")
ok = fail = skip = 0
for name, i, status, msg in results:
    mark = {"ok": "PASS", "fail": "FAIL", "skipped": "SKIP"}[status]
    extra = f"  {msg}" if msg and status != "ok" else ""
    print(f"{mark:4} {name} cell {i}{extra}")
    ok += status == "ok"
    fail += status == "fail"
    skip += status == "skipped"
print(f"\n{ok} passed, {fail} failed, {skip} skipped")
print("HTML outputs:")
for p in saved_figs:
    print(" -", p)
if fail:
    sys.exit(1)
