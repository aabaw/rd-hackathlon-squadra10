"""Motore di Linkin Prompt.

L'AI (modello locale) CAPISCE i testi: categoria, priorità, task, area e criticità di un invito, e SCRIVE le bozze.
Le REGOLE (codice, trasparenti e verificabili) DECIDONO: punteggio di utilità, accetta / delega / rilancia / rifiuta.
Così ogni decisione si può spiegare alla persona e a un auditor.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

import llm

DATI = Path(__file__).parent / "data"
RISULTATI = DATI / "risultati.json"
RISULTATI_FINTI = DATI / "risultati_finto.json"
FMT = "%Y-%m-%d %H:%M"


# ----------------------------------------------------------------------------- cosa estrae l'AI
class EmailAI(BaseModel):
    categoria: Literal["urgente", "cliente", "interno", "amministrativo", "newsletter"]
    priorita: int = Field(ge=1, le=5, description="1 = può aspettare, 5 = da gestire subito")
    riassunto: str = Field(description="una frase")
    tasks: list[str] = Field(description="azioni concrete per la destinataria, vuoto se nessuna")
    scadenza: str | None = Field(description="data YYYY-MM-DD se c'è una scadenza, altrimenti null")
    richiesta_meeting: bool = Field(description="il mittente chiede di fissare un incontro")
    attende_risposta: bool = Field(description="il mittente sta aspettando una risposta della destinataria")


class InvitoAI(BaseModel):
    area: Literal["strategico", "delivery", "tecnico", "legale", "finanziario"]
    tipo: Literal["decisionale", "operativo", "informativo", "one_to_one", "cliente"]
    criticita: int = Field(ge=1, le=5, description="1 = informativo, 5 = decisioni importanti")
    presenza: Literal["indispensabile", "opzionale"] = Field(description="serve davvero LEI di persona?")
    rimandabile: bool = Field(description="la riunione si può spostare senza danni")
    chiarezza_agenda: int = Field(ge=1, le=5, description="1 = agenda vaga, 5 = obiettivo e decisioni chiari")
    decisioni_richieste: bool
    riassunto: str = Field(description="una frase")


COMPETENZA = {"strategico": "Competenza strategica", "delivery": "Competenza di delivery", "tecnico": "Competenza tecnica",
              "legale": "Competenza legale", "finanziario": "Competenza finanziaria"}


def entita_note(persone: dict) -> list[tuple[str, str]]:
    """Persone e aziende che conosciamo già (utente, team, rubrica): la base dell'anonimizzazione."""
    out = []
    nomi = [persone["utente"]["nome"]] + [p["nome"] for p in persone["team"]]
    for r in persone["rubrica"].values():
        if r["stakeholder"] in ("ceo", "top_management", "cliente_strategico", "manager", "collega") and len(r["nome"].split()) == 2 \
                and r["reparto"] not in ("HR",):
            nomi.append(r["nome"])
        else:
            out.append((r["nome"], "Azienda"))
        out += [(m, "Azienda") for m in re.findall(r"([A-Z][\w]+ S\.p\.A\.)", r["ruolo"])]
    for n in set(nomi):
        nome, cognome = n.split()[0], n.split()[-1]
        out += [(n, "Persona"), (nome, "Nome"), (cognome, "Cognome")]
    for dom in {e.split("@")[1].split(".")[0] for e in persone["rubrica"]}:   # orbis, nexa, ticketpro...
        out.append((dom.capitalize(), "Azienda"))
    return out


def carica():
    persone = json.loads((DATI / "persone.json").read_text(encoding="utf-8"))
    casella = json.loads((DATI / "casella.json").read_text(encoding="utf-8"))
    return persone, casella


# ----------------------------------------------------------------------------- calendario
def _dt(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def libero(occupato: list[dict], inizio: datetime, fine: datetime) -> bool:
    return all(fine <= _dt(o["inizio"]) or inizio >= _dt(o["fine"]) for o in occupato)


def primo_slot(occupato: list[dict], da: datetime, minuti: int, giorni: int = 5) -> tuple[datetime, datetime] | None:
    """Primo spazio libero in orario d'ufficio (9-18), giorni feriali, a passi di 30 minuti."""
    t = da
    fine_ricerca = da + timedelta(days=giorni)
    while t < fine_ricerca:
        f = t + timedelta(minutes=minuti)
        if t.weekday() < 5 and t.hour >= 9 and (f.hour, f.minute) <= (18, 0) and f.date() == t.date() and libero(occupato, t, f):
            return t, f
        t += timedelta(minutes=30)
    return None


# ----------------------------------------------------------------------------- regole sugli inviti
PESO_STAKEHOLDER = {"ceo": 40, "top_management": 35, "cliente_strategico": 35, "manager": 20, "collega": 10, "esterno": 5}
TOP = {"ceo", "top_management", "cliente_strategico"}
LIVELLO = {"junior": 1, "mid": 2, "senior": 3}


PESI = {"stakeholder": 1, "rilevanza": 1, "criticita": 1, "presenza": 1, "urgenza": 1, "chiarezza": 1,
        "ridondanza": 1, "conflitto": 1, "platea": 1}      # configurabili dall'utente (anche dal vivo nella dashboard)
SOGLIA_CARICO_H = 12   # oltre queste ore di riunione a settimana un collega non riceve altre deleghe a cuor leggero


def ore_occupate(occupato: list[dict], giorno: str) -> float:
    return sum((_dt(o["fine"]) - _dt(o["inizio"])).total_seconds() / 3600 for o in occupato if o["inizio"].startswith(giorno))


def punteggio(invito: dict, ai: dict, persone: dict, pesi: dict | None = None) -> dict:
    """Punteggio di utilità 0-100 per la MIA presenza: somma pesata di voci leggibili (niente scatola nera)."""
    pesi = {**PESI, **(pesi or {})}
    utente, rubrica = persone["utente"], persone["rubrica"]
    org = rubrica.get(invito["organizzatore"], {"stakeholder": "esterno"})
    stesso_reparto = [e for e in invito["invitati"]
                      if e != utente["email"] and rubrica.get(e, {}).get("reparto") == utente["reparto"]]
    inizio, fine = _dt(invito["inizio"]), _dt(invito["fine"])
    voci = {   # chiave del peso -> (etichetta, valore grezzo)
        "stakeholder": ("Chi organizza", PESO_STAKEHOLDER[org["stakeholder"]]),
        "rilevanza": ("Rilevanza per il tuo ruolo", 25 if ai["area"] in utente["aree"] else 5),
        "criticita": ("Criticità dell'agenda", ai["criticita"] * 5),
        "presenza": ("Presenza richiesta", 10 if ai.get("presenza") == "indispensabile" else -10),
        "urgenza": ("Urgenza", -5 if ai.get("rimandabile", True) else 8),
        "chiarezza": ("Chiarezza dell'agenda", (ai.get("chiarezza_agenda", 3) - 3) * 3),
        "ridondanza": ("Colleghi del tuo team già invitati", -min(21, 7 * len(stesso_reparto))),
        "conflitto": ("Giornata già carica o sovrapposta",
                      (0 if libero(utente["calendario"], inizio, fine) else -12)
                      - min(12, round(4 * ore_occupate(utente["calendario"], invito["inizio"][:10])))),
        "platea": ("Più di 15 invitati", -10 if invito["n_invitati"] > 15 else 0),
    }
    totale = max(0, min(100, round(sum(pesi[k] * v for k, (_, v) in voci.items()))))
    return {"totale": totale, "voci": {lab: v for _, (lab, v) in voci.items()},
            "grezze": {k: v for k, (_, v) in voci.items()}, "ridondanza": len(stesso_reparto)}


def scegli_delegato(invito: dict, ai: dict, persone: dict) -> dict | None:
    """Delegation Fit Score: competenza, autonomia adatta alla criticità, disponibilità e carico, bonus crescita junior.
    Mai un junior da solo davanti a un cliente: con un cliente serve almeno un mid."""
    inizio, fine = _dt(invito["inizio"]), _dt(invito["fine"])
    org = persone["rubrica"].get(invito["organizzatore"], {"reparto": ""})
    minimo = 3 if ai["criticita"] >= 4 else 2 if ai["criticita"] == 3 else 1
    if org.get("reparto") == "Cliente":
        minimo = max(minimo, 2)
    migliore = None
    for p in persone["team"]:
        if ai["area"] not in p["competenze"] or p["email"] in invito["invitati"] or LIVELLO[p["seniority"]] < minimo \
                or not libero(p["occupato"], inizio, fine):
            continue
        carico = p.get("carico_settimanale_h", 0)
        voci = {COMPETENZA[ai["area"]]: 40,
                "Autonomia adatta alla criticità": 25,
                "Libero a quell'ora": 20,
                f"Carico settimanale ({carico:g} h)": 10 if carico <= SOGLIA_CARICO_H else -10,
                "Occasione di crescita (junior)": 15 if p["seniority"] == "junior" and ai["criticita"] <= 2 else 0}
        fit = sum(voci.values())
        if migliore is None or (fit, -carico) > (migliore["fit"], -migliore["carico"]):
            migliore = {**p, "fit": fit, "fit_voci": voci, "carico": carico}
    return migliore


def scelta(top: bool, libera: bool, totale: int, ridondanza: int, delegato: dict | None, chiarezza: int = 3) -> str:
    """L'albero di decisione, identico a quello che la dashboard ricalcola quando l'utente cambia i pesi."""
    if top:
        return "ACCETTA" if libera else "RILANCIA"
    if totale >= 60 and libera:
        return "ACCETTA"
    if chiarezza <= 2:          # agenda vaga o assente: prima di decidere si chiede l'agenda (Action Agent del documento)
        return "RILANCIA"
    if ridondanza >= 3:
        return "RIFIUTA"
    return "DELEGA" if delegato else "RIFIUTA"


def decidi(invito: dict, ai: dict, persone: dict, pesi: dict | None = None) -> dict:
    utente, rubrica = persone["utente"], persone["rubrica"]
    org = rubrica.get(invito["organizzatore"], {"stakeholder": "esterno", "nome": invito["organizzatore"]})
    inizio, fine = _dt(invito["inizio"]), _dt(invito["fine"])
    sono_libera = libero(utente["calendario"], inizio, fine)
    p = punteggio(invito, ai, persone, pesi)
    conflitto = "" if sono_libera else next(
        o["titolo"] for o in utente["calendario"] if not libero([o], inizio, fine))
    d = scegli_delegato(invito, ai, persone)
    slot = None if sono_libera else primo_slot(utente["calendario"], inizio, int((fine - inizio).total_seconds() // 60))
    prop = f"{slot[0]:%d/%m alle %H:%M}" if slot else "un altro orario"
    base_dati = {"punteggio": p, "top": org["stakeholder"] in TOP, "libera": sono_libera,
                 "candidato": {k: d[k] for k in ("nome", "ruolo", "seniority", "fit", "fit_voci", "carico")} if d else None,
                 "proposta": prop}
    azione = scelta(base_dati["top"], sono_libera, p["totale"], p["ridondanza"], d, ai.get("chiarezza_agenda", 3))
    base = f"Importanza {p['totale']}/100" + (f", si sovrappone a «{conflitto}»" if conflitto else "")
    if azione == "ACCETTA":
        mot = f"La organizza {org.get('nome', '')} ({org['ruolo']}): ci devi essere tu" if base_dati["top"] else base
        return {**base_dati, "azione": azione, "motivo": mot}
    if azione == "RILANCIA" and not base_dati["top"]:
        return {**base_dati, "azione": azione, "variante": "agenda",
                "motivo": "L'agenda non dice di cosa si parla: prima di decidere chiedo l'agenda e l'obiettivo"}
    if azione == "RILANCIA":
        return {**base_dati, "azione": azione, "motivo": f"Riunione importante, ma si sovrappone a «{conflitto}»: propongo il {prop}"}
    if azione == "DELEGA":
        return {**base_dati, "azione": azione, "delegato": base_dati["candidato"],
                "motivo": f"{base}. La passo a {d['nome']} ({d['ruolo']}), la persona più adatta ({d['fit']} su 110)"}
    extra = f" e ci sono già {p['ridondanza']} colleghi del tuo team" if p["ridondanza"] >= 3 else ""
    return {**base_dati, "azione": azione, "motivo": f"{base}{extra}: rifiuto e chiedo il verbale"}


# ----------------------------------------------------------------------------- prompt
def _sistema(utente: dict, oggi: str) -> str:
    return (f"Sei l'assistente personale di {utente['nome']}, {utente['ruolo']} ({utente['reparto']}). "
            f"Oggi è giovedì {oggi}. Rispondi in italiano. Non inventare nomi, date, promesse o fatti che non sono nel testo.")


CRITERI_EMAIL = """Criteri:
- categoria: urgente = problema in corso o scadenza OGGI; cliente = richiesta di un cliente non urgente;
  interno = colleghi o direzione; amministrativo = contratti, licenze, fatture; newsletter = comunicazione di massa
  senza richieste personali (anche quelle dell'HR a tutti).
- priorita: 5 = da fare oggi o problema bloccante; 4 = richiesta personale di CEO, cliente o collega che aspetta lei
  in settimana; 3 = scadenza amministrativa; 2 = utile ma non urgente; 1 = newsletter o informativa.
- tasks: solo azioni che deve fare LEI, brevi; lista vuota per le newsletter.
- scadenza: data AAAA-MM-GG calcolata da oggi, oppure null se non c'è una data precisa.
- richiesta_meeting: true SOLO se chiede esplicitamente di fissare un incontro o una demo.
- attende_risposta: true SOLO se il mittente aspetta una risposta personale da lei."""

CRITERI_INVITO = """Criteri:
- area: strategico = direzione, priorità aziendali, investimenti; delivery = avanzamento di progetti e rilasci;
  tecnico = sviluppo, sprint, strumenti, webinar di prodotto; legale = contratti, clausole, penali, SLA;
  finanziario = costi, budget, consuntivi.
- criticita: 5 = decisioni importanti per l'azienda o per un cliente; 4 = decisioni su contratti o rischi;
  3 = revisione di numeri o stato; 2 = aggiornamento di routine del team; 1 = presentazione o webinar informativo.
- tipo: decisionale = si decide qualcosa; operativo = stato del lavoro; informativo = presentazione o webinar;
  one_to_one = due persone; cliente = incontro con un cliente.
- presenza: indispensabile SOLO se serve proprio lei (decide lei, o la vuole il CEO o un cliente); altrimenti opzionale.
- rimandabile: true se spostarla di qualche giorno non fa danni.
- chiarezza_agenda: 5 = obiettivo e decisioni scritti chiaramente; 1 = agenda vaga o assente."""


def _bozza_invito(invito, decisione, persone, oggi) -> str:
    utente = persone["utente"]
    org = persone["rubrica"].get(invito["organizzatore"], {"nome": invito["organizzatore"]})
    a = decisione["azione"]
    if a == "ACCETTA":
        cosa = "conferma la partecipazione"
    elif a == "RILANCIA" and decisione.get("variante") == "agenda":
        cosa = "chiede gentilmente l'agenda e l'obiettivo della riunione prima di confermare la partecipazione"
    elif a == "RILANCIA":
        cosa = f"spiega che a quell'ora è già impegnata e propone in alternativa {decisione['proposta']}"
    elif a == "DELEGA":
        d = decisione["delegato"]
        cosa = f"comunica che parteciperà al suo posto {d['nome']} ({d['ruolo']}), che ha le competenze per decidere, in copia"
    else:
        cosa = "declina con garbo spiegando che il team è già ben rappresentato, e chiede di ricevere il verbale"
    sistema = _sistema(utente, oggi) + " Scrivi email brevi (massimo 5 righe), cortesi e professionali, firmate col suo nome."
    d0 = _dt(invito['inizio'])
    decisione["giorno"] = GIORNI[d0.weekday()]      # il giorno della settimana lo scrive il codice, non il modello
    richiesta = (f"Riunione: «{invito['titolo']}» di {GIORNI[d0.weekday()]} {d0:%d/%m} alle {d0:%H:%M}, organizzata da {org['nome']}.\n"
                 f"DECISIONE GIÀ PRESA, da rispettare: {cosa}.\nScrivi la risposta all'organizzatore. Solo il testo dell'email, senza oggetto.")
    testo = llm.testo(sistema, richiesta, cosa=f"bozza {invito['id']}")
    problemi = controlla_bozza(testo, decisione)
    if problemi:   # rete di sicurezza: una seconda prova con l'errore spiegato, poi il testo sicuro scritto dal codice
        testo = llm.testo(sistema, richiesta + f"\nLa bozza precedente era sbagliata: {'; '.join(problemi)}. Correggila.",
                          cosa=f"bozza {invito['id']} (correzione)")
        if controlla_bozza(testo, decisione):
            decisione["controllo"] = "testo sicuro"
            return _testo_sicuro(invito, decisione, utente, org)
        decisione["controllo"] = "corretta al 2° tentativo"
    else:
        decisione["controllo"] = "ok"
    return testo


CONFERMA = re.compile(r"(?<!non )(conferm\w* (la (mia )?|di )?(partecipa|presen)|parteciperò|sarò presente)", re.I)


GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def controlla_bozza(testo: str, dec: dict) -> list[str]:
    """La frase decisiva non si lascia al modello senza controllo: deve dire la stessa cosa della regola."""
    a, p = dec["azione"], []
    sbagliati = [g for g in GIORNI if g in testo.lower() and g != dec.get("giorno")]
    if dec.get("giorno") and sbagliati:
        p.append(f"scrive «{sbagliati[0]}» ma la riunione è {dec['giorno']}")
    if a != "ACCETTA" and CONFERMA.search(testo):
        p.append("conferma la partecipazione ma la decisione è " + a.lower())
    if a == "DELEGA" and dec["delegato"]["nome"].split()[0] not in testo:
        p.append(f"non nomina il delegato {dec['delegato']['nome']}")
    if a == "RILANCIA" and dec.get("variante") == "agenda":
        if "agenda" not in testo.lower():
            p.append("non chiede l'agenda")
    elif a == "RILANCIA" and dec.get("proposta", "").split(" alle ")[-1] not in testo:
        p.append(f"non propone l'orario {dec.get('proposta')}")
    if a == "RIFIUTA" and "verbale" not in testo.lower():
        p.append("non chiede il verbale")
    if (x := re.search(r"\[[^\]]{3,}\]", testo)):   # es. «Gentile [Nome Organizzatore]»: un segnaposto non va mai a un cliente
        p.append(f"contiene il segnaposto {x[0]}")
    return p


def _testo_sicuro(invito, dec, utente, org) -> str:
    nome = org["nome"].split()[0] if org.get("stakeholder") != "esterno" else ""
    saluto = f"Buongiorno {nome}," if nome else "Buongiorno,"
    corpo = {
        "ACCETTA": "confermo volentieri la mia partecipazione.",
        "RILANCIA": ("prima di confermare mi mandi l'agenda e l'obiettivo dell'incontro?" if dec.get("variante") == "agenda"
                     else f"a quell'ora ho già un impegno: possiamo spostarci al {dec.get('proposta')}?"),
        "DELEGA": (f"al mio posto parteciperà {dec['delegato']['nome']} ({dec['delegato']['ruolo']}), che ha le competenze "
                   "per decidere; la metto in copia." if dec["azione"] == "DELEGA" else ""),
        "RIFIUTA": "il team è già ben rappresentato, quindi non parteciperò: mi mandate il verbale?",
    }[dec["azione"]]
    return f"{saluto}\nper «{invito['titolo']}» {corpo}\nGrazie,\n{utente['nome']}"


# ----------------------------------------------------------------------------- finto modello per prove e riserva
def _finto_email(e):
    a = e["_atteso"]
    return {"categoria": a["categoria"], "priorita": a["priorita"], "riassunto": e["oggetto"], "tasks": [],
            "scadenza": None, "richiesta_meeting": e["id"] == "E6", "attende_risposta": e["id"] == "E5"}


def _finto_invito(i):
    c = i["_atteso"]["criticita"]
    return {**i["_atteso"], "decisioni_richieste": c >= 4, "riassunto": i["agenda"],
            "tipo": "decisionale" if c >= 4 else "informativo" if c == 1 else "operativo",
            "presenza": "indispensabile" if c >= 4 else "opzionale", "rimandabile": c <= 3,
            "chiarezza_agenda": i["_atteso"].get("chiarezza_agenda", 4)}


# ----------------------------------------------------------------------------- pipeline completa
def elabora(finto: bool = False, avanzamento=None, solo_inviti: bool = False) -> dict:
    persone, casella = carica()
    utente, oggi = persone["utente"], persone["oggi"]
    sistema = _sistema(utente, oggi)
    llm.statistiche.clear()
    llm.imposta_anonimizzazione(entita_note(persone))
    if not finto and not (llm.locale() and "Azure" not in llm.FORNITORE):   # modello remoto: l'AI locale cerca anche i nomi sconosciuti
        extra = [(x, "Nome") for m in casella["email"] + casella["inviti"]
                 for x in llm.scopri_entita(m.get("testo") or m.get("agenda", "")) if x not in llm.ANON]
        llm.imposta_anonimizzazione(entita_note(persone) + extra)
    t0 = time.perf_counter()
    passi = len(casella["email"]) + 2 * len(casella["inviti"]) + 2
    fatti = 0

    def passo(nome):
        nonlocal fatti
        fatti += 1
        if avanzamento:
            avanzamento(fatti / passi, nome)

    prima = json.loads(RISULTATI.read_text(encoding="utf-8")) if solo_inviti and RISULTATI.exists() else None
    email_out = list(prima["email"]) if prima else []
    for e in ([] if prima else casella["email"]):
        mitt = persone["rubrica"].get(e["da"], {"nome": e["da"], "ruolo": "", "stakeholder": "esterno"})
        if finto:
            ai = _finto_email(e)
        else:
            ai = llm.json_validato(EmailAI, sistema + " Classifica l'email per la destinataria.\n" + CRITERI_EMAIL,
                                   f"Da: {mitt['nome']} ({mitt['ruolo']})\nData: {e['data']}\nOggetto: {e['oggetto']}\n\n{e['testo']}",
                                   cosa=f"classifica {e['id']}").model_dump()
            # la data la tiene solo se è davvero una data: il resto («media», «Immediata») non entra nell'agenda
            m = re.search(r"\d{4}-\d{2}-\d{2}", ai["scadenza"] or "")
            ai["scadenza"] = m.group(0) if m else None
            if ai["categoria"] == "newsletter":
                ai["tasks"] = []
        regola = ""
        if mitt["stakeholder"] in TOP and ai["categoria"] != "newsletter" and ai["priorita"] < 4:
            ai["priorita"], regola = 4, "alzata a 4: mittente CEO o cliente strategico"
        giorni = (datetime.strptime(oggi, "%Y-%m-%d").date() - _dt(e["data"]).date()).days
        email_out.append({**e, "mittente": mitt, "ai": ai, "regola": regola,
                          "sollecito": ai["attende_risposta"] and giorni >= 1, "giorni": giorni})
        passo(f"email {e['id']}")

    # richieste di incontro arrivate per email → bozza d'invito nel primo slot libero (settimana prossima)
    for e in ([] if prima else email_out):
        if e["ai"]["richiesta_meeting"]:
            slot = primo_slot(utente["calendario"], datetime(2026, 11, 30, 9, 0), 45)
            e["slot"] = f"{slot[0]:%d/%m/%Y %H:%M}-{slot[1]:%H:%M}" if slot else None
            e["bozza_invito"] = ("[bozza simulata] Proposta di demo il " + (e["slot"] or "?")) if finto else llm.testo(
                sistema + " Scrivi email brevi (massimo 5 righe), firmate col suo nome.",
                f"{e['mittente']['nome']} chiede un incontro: «{e['oggetto']}». Proponi l'incontro il {e['slot']} (online) "
                f"e chiedi conferma. Non aggiungere altro: nessuna promessa, nessun altro argomento. Solo il testo dell'email.",
                cosa=f"invito da {e['id']}")
    passo("bozze d'invito")

    inviti_out = []
    for i in casella["inviti"]:
        org = persone["rubrica"].get(i["organizzatore"], {"nome": i["organizzatore"], "ruolo": "", "stakeholder": "esterno"})
        if finto:
            ai = _finto_invito(i)
        else:
            ai = llm.json_validato(InvitoAI, sistema + " Analizza l'invito a una riunione.\n" + CRITERI_INVITO,
                                   f"Titolo: {i['titolo']}\nOrganizzatore: {org['nome']} ({org['ruolo']})\n"
                                   f"Quando: {i['inizio']} - {i['fine']}\nInvitati: {i['n_invitati']}\nAgenda: {i['agenda']}",
                                   cosa=f"analizza {i['id']}").model_dump()
        passo(f"invito {i['id']}")
        dec = decidi(i, ai, persone)
        dec["bozza"] = f"[bozza simulata] {dec['azione']} — {i['titolo']}" if finto else _bozza_invito(i, dec, persone, oggi)
        inviti_out.append({**i, "organizzatore_info": org, "ai": ai, **dec})
        passo(f"bozza {i['id']}")

    news = [e for e in email_out if e["ai"]["categoria"] == "newsletter"]
    digest = prima["digest"] if prima else "[sintesi simulata]" if finto or not news else llm.testo(
        sistema, "Riassumi in 3 punti brevi, da leggere a fine giornata:\n\n" +
        "\n\n".join(f"{e['oggetto']}: {e['testo']}" for e in news), cosa="sintesi newsletter")
    passo("sintesi newsletter")

    risultato = {"meta": {"modello": "finto (prova)" if finto else llm.MODEL, "server": llm.BASE_URL, "locale": llm.locale() and "Azure" not in llm.FORNITORE,
                          "anonimizzazione": {"entita": len(llm.ANON), "esempio": llm.anonimizza(casella["email"][1]["testo"])}, "fornitore": llm.FORNITORE, "ragionamento": llm.REASONING,
                          "quando": datetime.now().strftime(FMT), "secondi": round(time.perf_counter() - t0, 1),
                          "chiamate": list(llm.statistiche)},
                 "email": email_out, "inviti": inviti_out, "digest": digest}
    # le prove col finto modello non devono mai sovrascrivere l'elaborazione vera
    (RISULTATI_FINTI if finto else RISULTATI).write_text(
        json.dumps(risultato, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return risultato


if __name__ == "__main__":
    import sys
    r = elabora(finto="--finto" in sys.argv, solo_inviti="--solo-inviti" in sys.argv, avanzamento=lambda f, n: print(f"{f:5.0%} {n}", flush=True))
    for i in r["inviti"]:
        print(i["id"], i["azione"], i["punteggio"]["totale"], "-", i["motivo"])
    print("secondi:", r["meta"]["secondi"])
