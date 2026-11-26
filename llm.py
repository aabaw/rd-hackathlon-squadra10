"""Unico punto che parla col modello. Qualunque server compatibile OpenAI: LM Studio in locale (default),
oppure il modello dell'azienda con la sua chiave API (OpenAI, Azure OpenAI, Anthropic, Ollama...).
La chiave resta solo in memoria: non si scrive su disco e non entra nei risultati."""
from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlparse

from openai import OpenAI
from pydantic import BaseModel, ValidationError

# Fornitori pronti: indirizzo compatibile OpenAI e un modello d'esempio (il modello lo sceglie chi usa la dashboard).
FORNITORI = {
    "LM Studio (locale)": ("http://127.0.0.1:18234/v1", "gemma-4-e4b-it-qat"),
    "Ollama (locale)": ("http://127.0.0.1:11434/v1", ""),
    "OpenAI": ("https://api.openai.com/v1", ""),
    "Azure OpenAI": ("https://linkin-prompt-ai.openai.azure.com/openai/v1/", "gpt-4.1-mini"),   # risorsa della squadra (26/11)
    "Anthropic (compatibilità OpenAI)": ("https://api.anthropic.com/v1/", ""),
    "Server Azure della squadra (tunnel SSH)": ("http://127.0.0.1:11434/v1", ""),
    "Altro compatibile OpenAI": ("", ""),
}

BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:18234/v1")
MODEL = os.getenv("LLM_MODEL", "gemma-4-e4b-it-qat")   # Gemma 4 E4B: il migliore in italiano nelle nostre prove (Qwen3.5-4B sbagliava)
# Qwen3.5 su LM Studio: senza reasoning_effort=none spende tutti i token a "pensare" e la risposta resta vuota.
REASONING = os.getenv("LLM_REASONING_EFFORT", "none")
_client = OpenAI(base_url=BASE_URL, api_key=os.getenv("LLM_API_KEY", "locale"), timeout=180)
statistiche: list[dict] = []          # una riga per chiamata: cosa, secondi, token
FORNITORE = "LM Studio (locale)"   # il nome scelto nella barra laterale, per dire la verità sulla privacy

# ---- Ingest con anonimizzazione (GDPR): nomi, aziende ed email diventano segnaposti PRIMA di arrivare al modello,
# qualunque esso sia, e tornano veri solo sul PC. La mappa non lascia mai questa macchina.
ANON: dict[str, str] = {}                      # vero -> segnaposto
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_client_locale = OpenAI(base_url="http://127.0.0.1:18234/v1", api_key="locale", timeout=120)   # l'AI locale dell'ingest


def imposta_anonimizzazione(entita: list[tuple[str, str]]) -> None:
    """entita = [(testo vero, tipo)], tipo es. Persona/Nome/Cognome/Azienda. Segnaposti stabili per tutta l'elaborazione."""
    ANON.clear()
    conta: dict[str, int] = {}
    for vero, tipo in sorted({e for e in entita if e[0].strip()}, key=lambda e: (-len(e[0]), e[0])):
        conta[tipo] = conta.get(tipo, 0) + 1
        ANON[vero] = f"[{tipo} {conta[tipo]}]"


def anonimizza(t: str) -> str:
    for vero, seg in sorted(ANON.items(), key=lambda kv: -len(kv[0])):
        t = t.replace(vero, seg)
    return EMAIL_RE.sub("[email]", t)


def ripristina(t: str) -> str:
    for vero, seg in sorted(ANON.items(), key=lambda kv: -len(kv[1])):
        t = t.replace(seg, vero)
    return t


def scopri_entita(testo: str) -> list[str]:
    """AI locale: trova nomi di persone e aziende che la rubrica non conosce (usata quando il modello d'analisi è remoto)."""
    try:
        r = _client_locale.chat.completions.create(
            model="gemma-4-e4b-it-qat", temperature=0, max_tokens=150,
            messages=[{"role": "user", "content": "Elenca SOLO i nomi propri di persone e di aziende presenti nel testo, "
                       "uno per riga, senza altro. Se non ce ne sono scrivi NESSUNO.\n\n" + testo}])
        righe = [x.strip(" -•*\t") for x in (r.choices[0].message.content or "").splitlines()]
        return [x for x in righe if x and x.upper() != "NESSUNO" and len(x) < 60]
    except Exception:
        return []


def configura(base_url: str, modello: str, chiave: str = "", ragionamento: str = "none") -> None:
    """Cambia modello al volo (barra laterale). Ragionamento: none/low/medium/high, inviato solo se diverso da vuoto."""
    global BASE_URL, MODEL, REASONING, _client
    BASE_URL, MODEL, REASONING = base_url.strip(), modello.strip(), ragionamento
    _client = OpenAI(base_url=BASE_URL, api_key=chiave or "locale", timeout=180)


def locale() -> bool:
    return (urlparse(BASE_URL).hostname or "") in ("127.0.0.1", "localhost", "::1")


def online() -> bool:
    try:
        _client.with_options(timeout=5).models.list()
        return True
    except Exception:
        return False


def prova() -> str:
    """Una chiamata minima per dire all'utente se modello e chiave funzionano (senza mai mostrare la chiave)."""
    try:
        t = time.perf_counter()
        r = _client.with_options(timeout=60).chat.completions.create(
            model=MODEL, max_tokens=20, messages=[{"role": "user", "content": "Rispondi solo: ok"}],
            **({"extra_body": {"reasoning_effort": REASONING}} if REASONING else {}))
        return f"risponde in {time.perf_counter() - t:.1f} s: «{(r.choices[0].message.content or '').strip()[:40]}»"
    except Exception as e:   # niente dettagli che possano contenere la chiave
        return f"errore: {type(e).__name__} {str(e)[:160]}".replace(_client.api_key, "***") if _client.api_key else f"errore: {type(e).__name__}"


def _chiama(system: str, user: str, schema: dict | None, max_tokens: int, cosa: str) -> str:
    extra = {"reasoning_effort": REASONING} if REASONING else {}
    kw = {}
    if schema:
        kw["response_format"] = {"type": "json_schema", "json_schema": {"name": "risposta", "schema": schema, "strict": True}}
    t = time.perf_counter()
    system, user = anonimizza(system), anonimizza(user)      # il modello non vede mai un nome vero
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        r = _client.chat.completions.create(model=MODEL, temperature=0.2, max_tokens=max_tokens, extra_body=extra, messages=msgs, **kw)
    except Exception as e:
        if not schema or "response_format" not in str(e) and "json_schema" not in str(e):
            raise
        # fornitore senza JSON con schema: si chiede il JSON nel testo, poi Pydantic lo valida lo stesso
        msgs[1]["content"] = user + "\n\nRispondi SOLO con un oggetto JSON valido con queste chiavi:\n" + json.dumps(schema, ensure_ascii=False)
        r = _client.chat.completions.create(model=MODEL, temperature=0.2, max_tokens=max_tokens, extra_body=extra, messages=msgs)
    out_tok = r.usage.completion_tokens if r.usage else None
    statistiche.append({"cosa": cosa, "secondi": round(time.perf_counter() - t, 1), "token_out": out_tok})
    testo = ripristina((r.choices[0].message.content or "").strip())   # i nomi veri tornano solo qui, sul PC
    if testo.startswith("```"):   # alcuni modelli cloud incorniciano il JSON
        testo = testo.strip("`").removeprefix("json").strip()
    return testo


def json_validato(modello: type[BaseModel], system: str, user: str, cosa: str) -> BaseModel:
    """Chiede un JSON che rispetta lo schema; se non è valido lo rimanda indietro con l'errore (una volta)."""
    schema = modello.model_json_schema()
    testo = _chiama(system, user, schema, 600, cosa)
    try:
        return modello.model_validate_json(testo)
    except (ValidationError, json.JSONDecodeError) as e:
        testo = _chiama(system, f"{user}\n\nLa tua risposta precedente non era valida ({e}). Rispondi SOLO con il JSON corretto.",
                        schema, 600, cosa + " (correzione)")
        return modello.model_validate_json(testo)


def testo(system: str, user: str, cosa: str, max_tokens: int = 260) -> str:
    return _chiama(system, user, None, max_tokens, cosa)
