"""Mette i risultati veri e le immagini dentro la pagina disegnata (dashboard.html) e la salva in static/ per lo schermo intero."""
from __future__ import annotations

import base64
import json
from pathlib import Path

QUI = Path(__file__).parent
STATIC = QUI / "static" / "dashboard.html"
IMG = QUI / "img"


def _js(dati) -> str:
    return json.dumps(dati, ensure_ascii=False, default=str).replace("</", "<\\/")


def _uri(p: Path) -> str:
    tipo = "png" if p.suffix == ".png" else "jpeg"
    return f"data:image/{tipo};base64," + base64.b64encode(p.read_bytes()).decode()


def immagini() -> dict:
    """img/ritratti/<Nome Cognome>.jpg diventano gli avatar; img/scene/*.jpg le foto di scena. Se mancano, la pagina usa sigle e fondi scuri."""
    return {"ritratti": {p.stem: _uri(p) for p in sorted((IMG / "ritratti").glob("*.jpg"))},
            "scene": {p.stem: _uri(p) for p in sorted((IMG / "scene").glob("*.jpg"))},
            "logo": _uri(IMG / "logo_sito.png") if (IMG / "logo_sito.png").exists() else ""}   # apertura, tempo, motore


def inietta(html: str, risultati: dict, persone: dict) -> str:
    return (html.replace("/*__DATI__*/null", _js(risultati)).replace("/*__PERSONE__*/null", _js(persone))
                .replace("/*__IMG__*/{}", _js(immagini())))


def costruisci(risultati: dict, persone: dict) -> str:
    html = inietta((QUI / "dashboard.html").read_text(encoding="utf-8"), risultati, persone)
    STATIC.parent.mkdir(exist_ok=True)
    STATIC.write_text(html, encoding="utf-8")
    return html
