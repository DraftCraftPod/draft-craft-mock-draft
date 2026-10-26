import json, sys
d = sys.argv[1]
load = lambda f: {int(k): v for k, v in json.load(open(f"{d}/{f}")).items()}
hill_vals = list(map(float, open(f"{d}/hill.txt").read().split()))
charts = {"jj": load("jj.json"), "hill": {i+1: v for i, v in enumerate(hill_vals)}, "fs": load("fs.json"),
          "harvard": load("harvard.json"), "stuart": load("stuart.json")}
N = 224
norm = {k: [round(c[p] / c[1] * 1000, 1) for p in range(1, N+1)] for k, c in charts.items()}
cons = [round(sum(norm[k][i] for k in norm) / len(norm), 1) for i in range(N)]
out = {"consensus": cons, **norm}
json.dump(out, open(f"{d}/values.json", "w"), separators=(",", ":"))
print("pick  " + "  ".join(f"{k:>8}" for k in out))
for p in [1, 2, 3, 5, 10, 16, 32, 33, 48, 64, 65, 96, 97, 128, 160, 192, 224]:
    print(f"{p:>4}  " + "  ".join(f"{out[k][p-1]:>8}" for k in out))
