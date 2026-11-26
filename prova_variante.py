"""Prova una variante di dashboard con i dati veri e la fotografa.
Uso:  .venv\\Scripts\\python prova_variante.py varianti\\NOME.html
Scrive static/v_NOME.html (aperta da http://localhost:8599/app/static/v_NOME.html)
e due screenshot: riferimenti/prove/NOME_1440.png e NOME_390.png
"""
import json
import os
import subprocess
import sys
from pathlib import Path

QUI = Path(__file__).parent
src = Path(sys.argv[1])
nome = src.stem
dati = QUI / "data" / "risultati.json"
if not dati.exists():
    dati = QUI / "data" / "risultati_finto.json"
R = json.loads(dati.read_text(encoding="utf-8"))
P = json.loads((QUI / "data" / "persone.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(QUI))
import vista  # noqa: E402  (stessa iniezione della pagina vera: dati, persone, immagini)
html = vista.inietta(src.read_text(encoding="utf-8"), R, P)
(QUI / "static").mkdir(exist_ok=True)
(QUI / "static" / f"v_{nome}.html").write_text(html, encoding="utf-8")
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
(QUI / "riferimenti" / "prove").mkdir(parents=True, exist_ok=True)
for w, h in [(1440, 2400), (390, 2400)]:
    png = QUI / "riferimenti" / "prove" / f"{nome}_{w}.png"
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--user-data-dir={os.environ.get('TEMP', '.')}\\lp-{nome}-{w}", f"--window-size={w},{h}",
                    "--virtual-time-budget=9000", f"--screenshot={png}",
                    f"http://localhost:8599/app/static/v_{nome}.html"], capture_output=True, timeout=120)
    print(png, "ok" if png.exists() else "MANCANTE")
