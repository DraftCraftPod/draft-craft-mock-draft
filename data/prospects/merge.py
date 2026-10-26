import json, re, sys
d = sys.argv[1]
def norm(n):
    n = n.lower().replace(".", "").replace("'", "")
    n = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", n.strip())
    return {"brauntae johnson": "tae johnson"}.get(n, n)
POS = {"DL":"IDL","DL1T":"IDL","DL3T":"IDL","DL5T":"IDL","OG":"IOL","OC":"IOL","OLB":"LB","ILB":"LB","WRS":"WR","CBN":"CB","PK":"K"}
SCH = {"Mississippi":"Ole Miss","California":"Cal"}
CLS = {"JR":"Junior","SR":"Senior","RJR":"RS Junior","RSR":"RS Senior","RSO":"RS Sophomore","SO":"Sophomore"}
tek = {}
for line in open(f"{d}/drafttek.txt"):
    r, name, pos, sch, ht, wt, cl = line.strip().split("|")
    if not line.strip(): continue
    f, i = re.match(r"(\d+)'(\d+)", ht).groups()
    tek[norm(name)] = dict(tek=int(r), name=name, pos=POS.get(pos,pos), school=SCH.get(sch,sch), ht=int(f)*12+int(i), wt=int(wt), cls=CLS.get(cl,cl))
out, seen = [], set()
for i, line in enumerate(open(f"{d}/consensus.txt"), 1):
    name, pos, sch = line.strip().split("|")
    t = tek.get(norm(name), {})
    out.append([name, POS.get(pos,pos), SCH.get(sch,sch), t.get("ht",0), t.get("wt",0), t.get("cls",""), i, t.get("tek",0)])
    seen.add(norm(name))
for k, t in sorted(tek.items(), key=lambda kv: kv[1]["tek"]):
    if k in seen: continue
    out.append([t["name"], t["pos"], t["school"], t["ht"], t["wt"], t["cls"], 0, t["tek"]])
miss = [o[0] for o in out[:100] if not o[7]]
print(len(out), "players; consensus w/o DraftTek match:", miss, file=sys.stderr)
print(json.dumps(out, separators=(",",":"), ensure_ascii=False).replace("],[", "],\n["))
