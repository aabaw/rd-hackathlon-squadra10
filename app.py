"""Linkin Prompt — Daily Briefing (Stand By Me × With or Without You).
Modello: locale di default (LM Studio), oppure il vostro LLM con chiave API, oppure il vostro server Azure.
Avvio:  .venv\\Scripts\\streamlit run app.py --server.enableStaticServing true
Schermo intero per il pitch:  http://localhost:8599/app/static/dashboard.html
La versione precedente, con i soli componenti Streamlit, è in app_classica.py.
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

import engine
import llm
import vista

st.set_page_config(page_title="Linkin Prompt", page_icon="🎸", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.stApp{background:#000}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding:0!important;max-width:100%!important}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🎸 Linkin Prompt")
    st.markdown("### Scegli l’AI")
    fornitore = st.selectbox("Chi fornisce l’AI", list(llm.FORNITORI), key="forn")
    url0, mod0 = llm.FORNITORI[fornitore]
    base = st.text_input("Indirizzo del servizio", value=url0, key=f"url-{fornitore}")
    modello = st.text_input("Nome del modello", value=mod0, key=f"mod-{fornitore}",
                            placeholder="il nome del modello o del deployment")
    chiave = st.text_input("Chiave di accesso (API)", type="password", key="chiave",
                           help="Resta solo in memoria per questa sessione: non viene salvata né scritta nei risultati.")
    ragion = st.selectbox("Profondità di ragionamento", ["none", "low", "medium", "high"], key="rag",
                          help="Più alta = risposte più ragionate e più lente (solo se il modello lo supporta).")
    if base and modello:
        # i modelli locali (Qwen su LM Studio) vogliono «none» esplicito; quelli cloud senza ragionamento non vogliono il parametro
        llm.configura(base, modello, chiave, ragion if ragion != "none" else ("none" if "18234" in base else ""))
        llm.FORNITORE = fornitore
    st.caption("🔒 I testi restano su questa macchina" if llm.locale() and "Azure" not in fornitore
               else f"☁️ I testi, con nomi ed email nascosti, vanno a: {fornitore}")
    if st.button("Prova connessione", use_container_width=True):
        st.write(llm.prova())
    if st.button("⚡ Rifai l’analisi con questa AI", use_container_width=True, disabled=not (base and modello)):
        barra = st.progress(0.0, "Avvio…")
        engine.elabora(avanzamento=lambda f, n: barra.progress(min(f, 1.0), f"{n}…"))
        st.rerun()
    st.markdown("[↗ Apri a schermo intero](/app/static/dashboard.html)")

if engine.RISULTATI.exists():
    R = json.loads(engine.RISULTATI.read_text(encoding="utf-8"))
else:
    R = engine.elabora(finto=True)
persone, _ = engine.carica()
components.html(vista.costruisci(R, persone), height=3100, scrolling=True)
