import re, json, sys
s = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
FIX = {"WSH": "WAS"}
picks, rnd = [], 0
for block in re.split(r'class="round-title"', s)[1:]:
    rnd += 1
    for row in re.findall(r'<tr><td class="pick-number">(\d+)</td>(.*?)</tr>', block, flags=re.S):
        no, body = int(row[0]), row[1]
        logos = re.findall(r'/nfl/([a-z]+)\.svg', body)
        owner = FIX.get(logos[0].upper(), logos[0].upper())
        orig = FIX.get(logos[1].upper(), logos[1].upper()) if len(logos) > 1 else owner
        picks.append([no, rnd, owner, orig])
print(json.dumps(picks), file=open(sys.argv[2], "w"))
from collections import Counter
print("picks", len(picks), "rounds", Counter(p[1] for p in picks))
print("teams", sorted({p[2] for p in picks} | {p[3] for p in picks}))
print("traded", sum(p[2] != p[3] for p in picks), [p for p in picks if p[2] != p[3]][:8])
print("nos sequential", [p[0] for p in picks] == list(range(1, len(picks)+1)))
