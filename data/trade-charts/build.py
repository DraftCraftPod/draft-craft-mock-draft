import json, sys
d = sys.argv[1]
load = lambda f: {int(k): v for k, v in json.load(open(f"{d}/{f}")).items()}
hill_vals = list(map(float, open(f"{d}/hill.txt").read().split()))
charts = {"jj": load("jj.json"), "hill": {i+1: v for i, v in enumerate(hill_vals)}, "fs": load("fs.json"),
          "harvard": load("harvard.json"), "stuart": load("stuart.json")}
# Picks run past #224 once compensatory picks are in (up to 32 of them plus special ones), so every chart goes to 262.
# Charts that stop earlier (Harvard and Stuart at 224, the rest at 256) continue the slope of their last ten picks,
# never dropping below half their last published value.
N = 262
def extend(c):
    last = max(c)
    if last >= N:
        return c
    slope, floor = (c[last] - c[last - 10]) / 10, c[last] / 2
    return {**c, **{p: max(floor, c[last] + slope * (p - last)) for p in range(last + 1, N + 1)}}
charts = {k: extend(c) for k, c in charts.items()}
norm = {k: [round(c[p] / c[1] * 1000, 1) for p in range(1, N+1)] for k, c in charts.items()}
cons = [round(sum(norm[k][i] for k in norm) / len(norm), 1) for i in range(N)]
out = {"consensus": cons, **norm}
json.dump(out, open(f"{d}/values.json", "w"), separators=(",", ":"))
print("pick  " + "  ".join(f"{k:>8}" for k in out))
for p in [1, 2, 3, 5, 10, 16, 32, 33, 48, 64, 65, 96, 97, 128, 160, 192, 224, 256, 262]:
    print(f"{p:>4}  " + "  ".join(f"{out[k][p-1]:>8}" for k in out))
