"""Controllo minimo delle regole (senza modello): ogni invito deve finire nell'azione attesa."""
from engine import elabora

ATTESE = {"M1": "ACCETTA", "M2": "RIFIUTA", "M3": "DELEGA", "M4": "DELEGA", "M5": "DELEGA", "M6": "RILANCIA", "M7": "RILANCIA"}

r = elabora(finto=True)
got = {i["id"]: i["azione"] for i in r["inviti"]}
assert got == ATTESE, got
dele = {i["id"]: i["delegato"]["nome"] for i in r["inviti"] if i["azione"] == "DELEGA"}
assert dele == {"M3": "Roberto Franco", "M4": "Maria Enrica Vittoria Asti", "M5": "Federico Saccente"}, dele
e6 = next(e for e in r["email"] if e["id"] == "E6")
assert e6["slot"] == "30/11/2026 11:00-11:45", e6["slot"]
assert next(e for e in r["email"] if e["id"] == "E5")["sollecito"]

# il percorso delle bozze vere (con il modello sostituito da una funzione che restituisce il prompt)
import engine, llm
llm.testo = lambda system, user, cosa, max_tokens=260: user
persone, _ = engine.carica()
for i in r["inviti"]:
    prompt = engine._bozza_invito(i, i, persone, persone["oggi"])
    assert i["titolo"] in prompt, prompt
    if i["azione"] == "DELEGA":
        assert i["delegato"]["nome"] in prompt
print("OK: regole e bozze verificate", got)

# la rete di sicurezza: la bozza vera di Qwen per M2 (un rifiuto che «conferma la partecipazione») deve essere fermata
m2 = next(i for i in r["inviti"] if i["id"] == "M2")
assert engine.controlla_bozza("Gentile Marco, confermo la partecipazione alla riunione del 30 novembre.", m2)
for i in r["inviti"]:   # il testo sicuro scritto dal codice passa sempre il controllo
    assert not engine.controlla_bozza(engine._testo_sicuro(i, i, persone["utente"], i["organizzatore_info"]), i), i["id"]
print("OK: rete di sicurezza verificata")

# funzioni dal documento dei compagni: fit del delegato, niente junior da solo col cliente, pesi configurabili
m3 = next(i for i in r["inviti"] if i["id"] == "M3")
cand = engine.scegli_delegato(m3, m3["ai"], persone)
assert cand["seniority"] != "junior" and cand["nome"] == "Roberto Franco" and cand["fit"] == 95, cand
assert engine.punteggio(m3, m3["ai"], persone, {k: 0 for k in engine.PESI})["totale"] == 0
assert engine.scelta(True, False, 99, 0, None) == "RILANCIA" and engine.scelta(False, True, 10, 3, cand) == "RIFIUTA"
print("OK: fit delegato, pesi e albero verificati")

# documento aggiornato: «chiedi agenda» e anonimizzazione dell'ingest
assert next(i for i in r["inviti"] if i["id"] == "M7")["variante"] == "agenda"
llm.imposta_anonimizzazione(engine.entita_note(persone))
t = "Ciao Mario, Pia Sgualdino di Orbis S.p.A. scrive a marta.bella@nexa.example per Maria"
a = llm.anonimizza(t)
assert not any(x in a for x in ("Mario", "Pia", "Sgualdino", "Orbis", "Maria", "@")), a
assert llm.ripristina(a) == t.replace("marta.bella@nexa.example", "[email]"), llm.ripristina(a)
print("OK: chiedi agenda e anonimizzazione verificate ->", a)
