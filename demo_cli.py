"""Terminal demo.  Usage (from ~/network-guardian-ids):
   python demo_cli.py            -> random flow
   python demo_cli.py attack     -> random attack flow
   python demo_cli.py benign     -> random benign flow
   python demo_cli.py 42626      -> that exact test-set row"""
import sys
from demo_core import Guardian
g = Guardian()
a = sys.argv[1] if len(sys.argv) > 1 else "any"
idx = int(a) if a.isdigit() else g.pick(a)
raw = g.raw_row(idx)
truth = "ATTACK" if g.test["Label_Binary"].iloc[idx] == 1 else "BENIGN"
print("=" * 60, f"\nINPUT: test flow #{idx}  (true label hidden from model: {truth})")
print("77 features, first 8 shown:")
for c, v in list(zip(g.cols, raw))[:8]:
    print(f"  {c:<32s}{v:>18.4f}")
print("  ...")
r = g.detect(raw)
print("=" * 60, f"\nMODEL OUTPUT: {r['label']}  (attack probability {r['prob']:.6f})")
print(f"Correct: {r['label'] == truth}\n" + "=" * 60 + "\n")
print(r["alert"])
