"""Controllo a occhio dei risultati del modello: categorie, priorità, decisioni, fit, bozze.
Uso:  .venv\\Scripts\\python controlla_risultati.py
"""
import json
from pathlib import Path

r = json.loads((Path(__file__).parent / "data" / "risultati.json").read_text(encoding="utf-8"))
m = r["meta"]
print("MODELLO", m["modello"], "| secondi", m["secondi"], "| chiamate", len(m["chiamate"]),
      "| correzioni", [c["cosa"] for c in m["chiamate"] if "correzione" in c["cosa"]])
ok = 0
for e in r["email"]:
    a, at = e["ai"], e["_atteso"]
    ok += a["categoria"] == at["categoria"]
    print(f'{e["id"]} {a["categoria"]:<14}(atteso {at["categoria"]:<14}) p{a["priorita"]}/{at["priorita"]} '
          f'scad={a["scadenza"]} sollecito={e["sollecito"]} tasks={a["tasks"]}')
print("categorie giuste", ok, "/", len(r["email"]))
ATTESE = {"M1": "ACCETTA", "M2": "RIFIUTA", "M3": "DELEGA", "M4": "DELEGA", "M5": "DELEGA", "M6": "RILANCIA"}
for i in r["inviti"]:
    a = i["ai"]
    fit = (i.get("delegato") or {}).get("fit")
    print(f'{i["id"]} {a["area"]}/{a.get("tipo")}/crit{a["criticita"]}/{a.get("presenza")}/rimand={a.get("rimandabile")}/chiar={a.get("chiarezza_agenda")} '
          f'-> {i["azione"]} (atteso {ATTESE[i["id"]]}) punteggio {i["punteggio"]["totale"]} fit={fit} controllo={i.get("controllo")}')
    print("    BOZZA:", i["bozza"].replace("\n", " / ")[:300])
