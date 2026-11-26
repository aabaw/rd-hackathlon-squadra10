# Linkin Prompt · Squadra #10 · R-FACTOR 2026

**Traccia 1 · With or Without You: l’assistente per le riunioni.**
Legge gli inviti del calendario (e le email che li riguardano), decide quali meritano il tempo del manager e prepara le risposte. Il manager approva.

L’AI capisce · le regole decidono · tu approvi.

## Come funziona
1. **Capisce**: un modello linguistico legge ogni invito e restituisce un JSON con schema (tipo di riunione, criticità, presenza richiesta, chiarezza dell’agenda). Prima di inviare il testo, nomi, aziende ed email vengono nascosti (`llm.anonimizza`).
2. **Decide**: un punteggio 0–100 con pesi regolabili, voce per voce, e un albero di decisione: accetta, delega al collega più adatto, propone un altro orario o chiede l’agenda, rifiuta chiedendo il verbale (`engine.py`).
3. **Scrive**: bozze di risposta; una rete di sicurezza blocca quelle che contraddicono la decisione, sbagliano il giorno o lasciano segnaposti (`engine.controlla_bozza`).
4. **Approvi**: human in the loop con tre livelli: solo suggerimenti, approvi tu, in automatico entro i tuoi limiti.

## Avvio
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py --server.enableStaticServing true
```
Schermo intero: `http://localhost:8501/app/static/dashboard.html`.

Modello: di default LM Studio in locale (`gemma-4-e4b-it-qat`, porta 18234). Dalla barra laterale si può scegliere un altro servizio compatibile OpenAI (Azure OpenAI, OpenAI, Ollama…) con la propria chiave: resta solo in memoria, non viene scritta su disco.

## File
| File | Cosa fa |
|---|---|
| `app.py` | pagina Streamlit e scelta del modello |
| `engine.py` | analisi, punteggio, delega, decisione, bozze, rete di sicurezza |
| `llm.py` | l’unico punto che parla col modello (anonimizza prima, ripristina dopo) |
| `vista.py`, `dashboard.html` | la dashboard con dati e immagini |
| `data/` | casella, persone e risultati **simulati** |
| `test_engine.py` | verifiche del motore: `python test_engine.py` |

Dati simulati: i nomi della giuria e degli ospiti di R-FACTOR compaiono nella demo per gioco; inviti ed email sono inventati. Nessuna foto di persone vere.
