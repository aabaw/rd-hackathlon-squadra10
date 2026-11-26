"""Rifà solo le bozze che nominano un giorno della settimana sbagliato (il resto di risultati.json resta)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import engine  # noqa: E402

R = json.loads(engine.RISULTATI.read_text(encoding="utf-8"))
persone, _ = engine.carica()
for i in R["inviti"]:
    giusto = engine.GIORNI[engine._dt(i["inizio"]).weekday()]
    if engine.controlla_bozza(i["bozza"], {**i, "giorno": giusto}):
        prima = i["bozza"]
        i["bozza"] = engine._bozza_invito(i, i, persone, persone["oggi"])
        print(i["id"], "rifatta:", i.get("controllo"), "|", i["bozza"].replace("\n", " / ")[:200])
engine.RISULTATI.write_text(json.dumps(R, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print("salvato")
