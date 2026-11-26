"""Linkin Prompt — Daily Briefing: email (Stand By Me) + inviti (With or Without You), tutto con AI locale.
Avvio:  .venv\\Scripts\\streamlit run app.py
"""
from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

import engine
import llm

st.set_page_config(page_title="Linkin Prompt", page_icon="🎸", layout="wide")

COLORI = {"ACCETTA": "#16a34a", "DELEGA": "#2563eb", "RILANCIA": "#d97706", "RIFIUTA": "#6b7280"}
ICONE = {"ACCETTA": "✅", "DELEGA": "🤝", "RILANCIA": "🔁", "RIFIUTA": "🙅"}
PRIO = {5: ("🔴", "Subito"), 4: ("🟠", "Oggi"), 3: ("🟡", "Questa settimana"), 2: ("🟢", "Quando puoi"), 1: ("⚪", "Fine giornata")}

st.markdown("""<style>
.pill{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-weight:600;font-size:.85rem}
.bar{height:10px;border-radius:5px}
.muted{color:#6b7280;font-size:.85rem}
.big{font-size:2.2rem;font-weight:800;line-height:1}
</style>""", unsafe_allow_html=True)


@st.cache_data
def carica_risultati(_versione: float) -> dict:
    if engine.RISULTATI.exists():
        return json.loads(engine.RISULTATI.read_text(encoding="utf-8"))
    return engine.elabora(finto=True)          # riserva: nessuna elaborazione vera ancora fatta


def versione() -> float:
    return engine.RISULTATI.stat().st_mtime if engine.RISULTATI.exists() else 0.0


inviati = st.session_state.setdefault("inviati", set())

# ----------------------------------------------------------------------------- barra laterale
with st.sidebar:
    st.markdown("## 🎸 Linkin Prompt")
    st.caption("Stand By Me × With or Without You")
    in_linea = llm.online()
    st.markdown(("🟢 AI locale attiva" if in_linea else "🔴 AI locale spenta") + f"  \n`{llm.MODEL}`")
    if st.button("⚡ Rielabora la casella con l'AI locale", disabled=not in_linea, use_container_width=True):
        barra = st.progress(0.0, "Avvio…")
        engine.elabora(avanzamento=lambda f, n: barra.progress(min(f, 1.0), f"{n}…"))
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("### 🎛️ Limiti di autonomia")
    st.caption("Cosa l'assistente può fare da solo. Tutto il resto resta una bozza da approvare.")
    auto_accetta = st.toggle("Accetta da solo", value=False)
    auto_delega = st.toggle("Delega da solo", value=True)
    auto_rifiuta = st.toggle("Rifiuta da solo…", value=True)
    soglia = st.slider("…solo sotto questo punteggio", 0, 100, 20, disabled=not auto_rifiuta)
    st.toggle("🔐 CEO e clienti strategici: sempre la mia approvazione", value=True, disabled=True)

R = carica_risultati(versione())
persone, _ = engine.carica()
utente = persone["utente"]


def stato(inv: dict) -> tuple[str, bool]:
    if inv["id"] in inviati:
        return "📨 Inviata da te", True
    if inv["organizzatore_info"].get("stakeholder") in engine.TOP:
        return "🔐 Serve la tua approvazione (stakeholder chiave)", False
    a, s = inv["azione"], inv["punteggio"]["totale"]
    if (a == "ACCETTA" and auto_accetta) or (a == "DELEGA" and auto_delega) or (a == "RIFIUTA" and auto_rifiuta and s < soglia):
        return "🤖 Gestita in autonomia (entro i tuoi limiti)", True
    return "✋ In attesa della tua approvazione", False


# ----------------------------------------------------------------------------- intestazione
oggi = datetime.strptime(persone["oggi"], "%Y-%m-%d")
st.markdown(f"# Buongiorno {utente['nome'].split()[0]} ☀️")
st.markdown(f"**Daily Briefing di giovedì {oggi:%d/%m/%Y}** · {utente['ruolo']}, {utente['reparto']}  \n"
            f"<span class='muted'>🔒 100% locale: modello `{R['meta']['modello']}` sul tuo PC, nessuna email esce dall'azienda · "
            f"elaborato il {R['meta']['quando']} in {R['meta']['secondi']} s</span>", unsafe_allow_html=True)

email = R["email"]
lavoro = sorted([e for e in email if e["ai"]["categoria"] != "newsletter"], key=lambda e: -e["ai"]["priorita"])
inviti = sorted(R["inviti"], key=lambda i: i["inizio"])
ore_liberate = sum((engine._dt(i["fine"]) - engine._dt(i["inizio"])).total_seconds() / 3600
                   for i in inviti if i["azione"] in ("DELEGA", "RIFIUTA"))
scadenze = [e for e in email if e["ai"].get("scadenza")]

c = st.columns(4)
c[0].metric("🔴 Subito", sum(e["ai"]["priorita"] == 5 for e in lavoro))
c[0].caption("email da gestire per prime")
c[1].metric("📅 Riunioni", len(inviti))
c[1].caption(f"{sum(i['azione'] in ('DELEGA', 'RIFIUTA') for i in inviti)} delegate o declinate")
c[2].metric("⏱️ Ore liberate", f"{ore_liberate:g} h".replace(".", ","))
c[2].caption("di riunioni, questa settimana")
c[3].metric("📌 Scadenze", len(scadenze))
c[3].caption(f"{sum(e['sollecito'] for e in email)} risposte che aspettano te")

t1, t2, t3, t4, t5 = st.tabs(["☀️ Priorità di oggi", "📅 Riunioni", "✅ Task e scadenze", "📰 Newsletter", "🧠 Come decide"])

# ----------------------------------------------------------------------------- priorità
with t1:
    for e in lavoro:
        ic, label = PRIO[e["ai"]["priorita"]]
        with st.container(border=True):
            a, b = st.columns([5, 2])
            a.markdown(f"**{ic} {e['oggetto']}**  \n<span class='muted'>{e['mittente']['nome']} · {e['mittente']['ruolo']} · {e['data']}</span>",
                       unsafe_allow_html=True)
            b.markdown(f"**{label}** · {e['ai']['categoria']}")
            st.write(e["ai"]["riassunto"])
            if e.get("regola"):
                st.caption(f"⚙️ Regola: {e['regola']}")
            if e["sollecito"]:
                st.warning(f"⏰ {e['mittente']['nome']} aspetta una tua risposta da {e['giorni']} giorni")
            for t in e["ai"]["tasks"]:
                st.checkbox(t, key=f"t1-{e['id']}-{t}")
            if e.get("bozza_invito"):
                with st.expander(f"📅 Ho preparato l'invito: {e['slot']}", expanded=True):
                    st.text_area("Bozza", e["bozza_invito"], key=f"bi-{e['id']}", height=140)
                    if st.button("Approva e invia", key=f"ok-{e['id']}"):
                        st.success("Invito inviato ✅ (simulazione: nessuna email reale)")

# ----------------------------------------------------------------------------- riunioni
with t2:
    for inv in inviti:
        a = inv["azione"]
        s, fatto = stato(inv)
        with st.container(border=True):
            sx, mid, dx = st.columns([4, 3, 4])
            sx.markdown(f"#### {inv['titolo']}")
            sx.markdown(f"🗓️ {engine._dt(inv['inizio']):%a %d/%m %H:%M}–{engine._dt(inv['fine']):%H:%M} · 👥 {inv['n_invitati']} invitati  \n"
                        f"👤 {inv['organizzatore_info']['nome']} — {inv['organizzatore_info'].get('ruolo', '')}")
            sx.caption(f"🤖 {inv['ai']['riassunto']}  \nArea **{inv['ai']['area']}** · criticità **{inv['ai']['criticita']}/5**")

            p = inv["punteggio"]
            mid.markdown(f"<div class='muted'>Utilità per te</div><div class='big'>{p['totale']}<span class='muted'>/100</span></div>",
                         unsafe_allow_html=True)
            for voce, v in p["voci"].items():
                if v:
                    colore = "#16a34a" if v > 0 else "#dc2626"
                    mid.markdown(f"<div class='muted'>{voce}: <b>{v:+d}</b></div>"
                                 f"<div class='bar' style='width:{min(abs(v), 40) * 2.5}%;background:{colore}'></div>",
                                 unsafe_allow_html=True)

            dx.markdown(f"<span class='pill' style='background:{COLORI[a]}'>{ICONE[a]} {a}</span>", unsafe_allow_html=True)
            dx.write(inv["motivo"])
            dx.markdown(f"**{s}**")
            with dx.expander("✉️ Bozza di risposta", expanded=not fatto):
                st.text_area("Testo", inv["bozza"], key=f"b-{inv['id']}", height=150)
                k1, k2 = st.columns(2)
                if k1.button("Approva e invia", key=f"ok-{inv['id']}", disabled=fatto):
                    inviati.add(inv["id"])
                    st.rerun()
                k2.button("Scarta", key=f"no-{inv['id']}")

# ----------------------------------------------------------------------------- task e scadenze
with t3:
    a, b = st.columns(2)
    with a:
        st.markdown("### ✅ Call to action dalle email")
        for e in lavoro:
            for t in e["ai"]["tasks"]:
                st.checkbox(f"{t}  ·  _{e['mittente']['nome']}_", key=f"t3-{e['id']}-{t}")
    with b:
        st.markdown("### 📌 Scadenze")
        for e in sorted(scadenze, key=lambda e: e["ai"]["scadenza"]):
            try:
                giorni = (datetime.strptime(e["ai"]["scadenza"], "%Y-%m-%d") - oggi).days
                quando = "oggi" if giorni == 0 else f"tra {giorni} giorni" if giorni > 0 else f"scaduta da {-giorni} giorni"
            except ValueError:
                quando = e["ai"]["scadenza"]
            st.markdown(f"**{e['ai']['scadenza']}** ({quando}) — {e['oggetto']}")
        st.markdown("### ⏰ Risposte che aspettano te")
        for e in email:
            if e["sollecito"]:
                st.markdown(f"- {e['mittente']['nome']}: «{e['oggetto']}» da {e['giorni']} giorni")

# ----------------------------------------------------------------------------- newsletter
with t4:
    st.markdown("### 📰 Da leggere a fine giornata")
    st.info(R["digest"])
    for e in email:
        if e["ai"]["categoria"] == "newsletter":
            st.markdown(f"- **{e['oggetto']}** — {e['mittente']['nome']}")

# ----------------------------------------------------------------------------- come decide
with t5:
    st.markdown("### L'AI capisce, le regole decidono, tu approvi")
    st.markdown("""
| Passo | Chi | Cosa |
|---|---|---|
| 1 | 🤖 AI locale | legge email e inviti: categoria, priorità, task, scadenze, area e criticità della riunione (JSON validato) |
| 2 | ⚙️ Regole trasparenti | calcolano il punteggio di utilità e scelgono accetta / delega / rilancia / rifiuta |
| 3 | 🤖 AI locale | scrive la bozza della risposta |
| 4 | 🙋 Tu | approvi, oppure l'assistente agisce da solo entro i limiti che hai fissato |
""")
    st.markdown("**Punteggio di utilità** = chi organizza (CEO 40, cliente strategico 35, manager 20, collega 10, esterno 5) "
                "+ rilevanza per il ruolo (25 / 5) + criticità × 5 − 7 per ogni collega del reparto già invitato (max −21) "
                "− 10 se la platea supera 15 persone.  \n"
                "**Delega intelligente**: competenza giusta, seniority sufficiente (criticità ≥ 4 → senior), calendario libero; "
                "con criticità ≤ 2 si preferisce un junior, come occasione di crescita.")
    ok_e = sum(e["ai"]["categoria"] == e["_atteso"]["categoria"] for e in email)
    ok_i = sum(i["ai"]["area"] == i["_atteso"]["area"] for i in inviti)
    st.markdown(f"**Accordo dell'AI con le etichette attese**: categorie email {ok_e}/{len(email)} · aree riunioni {ok_i}/{len(inviti)}")
    ch = R["meta"]["chiamate"]
    if ch:
        st.markdown(f"**Prestazioni sul PC (solo CPU)**: {len(ch)} chiamate, media {sum(c['secondi'] for c in ch) / len(ch):.1f} s "
                    f"a chiamata, totale {R['meta']['secondi']} s")
        st.dataframe(ch, use_container_width=True, hide_index=True)
