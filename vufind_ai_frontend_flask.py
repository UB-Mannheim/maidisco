#!/usr/bin/env python3

import json
import os
import re
from urllib.parse import urlparse

import markdown
import nh3
import requests
from dotenv import load_dotenv
from flask import Flask, abort, render_template_string, request
from markupsafe import Markup
from openai import OpenAI

load_dotenv()

# --- Configuration ---
DEBUGMODE = os.environ.get("DEBUGMODE", False)
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = os.environ.get("PORT", "5001")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_API_URL = os.environ.get("OPENAI_API_URL")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")
VUFIND_SEARCH_ENDPOINT = os.environ.get(
    "VUFIND_SEARCH_ENDPOINT", "https://your-vufind-instance.example.com/api/search"
)

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")

client = OpenAI(base_url=OPENAI_API_URL, api_key=OPENAI_API_KEY)  # Required but unused

app = Flask(__name__)

# --- CSRF Protection ---
@app.before_request
def csrf_check():
    """Validate Sec-Fetch-Site header to prevent CSRF attacks."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("Origin")
    site = request.headers.get("Sec-Fetch-Site", "")
    # Modern browsers: same-origin or none (direct navigation) are safe
    if site in ("same-origin", "none"):
        return
    # API clients (curl, etc.) typically don't send Sec-Fetch-Site
    if not site and not origin:
        return
    # Older browsers: check if Origin matches host
    if origin:
        origin_host = urlparse(origin).hostname
        if origin_host == request.host:
            return
    abort(403, "CSRF-Validierung fehlgeschlagen")


# --- HTML Sanitization ---
# Markdown-relevant tags allowed in LLM summaries
MD_ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "a", "img",
    "ul", "ol", "li",
    "blockquote",
    "pre", "code",
    "em", "strong", "b", "i", "u", "s", "del", "ins",
    "table", "thead", "tbody", "tr", "th", "td",
    "dl", "dt", "dd",
    "sub", "sup",
}

MD_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start", "type"},
}

# --- HTML Template ---
INDEX_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>VuFind AI Search</title>
<style>
body { font-family: Arial; margin: 2rem; }
input, select, textarea { width: 100%; padding: 0.5rem; margin-bottom: 0.5rem; }
button { padding: 0.5rem 1rem; }
.result { border: 1px solid #ddd; padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 6px; }
.meta { color: #666; font-size: 0.9rem; }
.summ { background: #f7f7f9; padding: 0.75rem; border-radius: 6px; margin-top: 1rem; }
</style>
</head>
<body>
<h1>VuFind AI Search Frontend</h1>
<form method="post" action="/search">
<label for="nl">Search (natural language)</label>
<textarea id="nl" name="nl" rows="3">{{example}}</textarea>

<label for="language">Language</label>
<select id="language" name="language">
  <option value="">Any</option>
  <option value="English">English</option>
  <option value="German">German</option>
  <option value="French">French</option>
</select>

<label for="material_type">Material type</label>
<select id="material_type" name="material_type">
  <option value="">Any</option>
  <option value="Books">Books</option>
  <option value="Articles">Articles</option>
  <option value="Theses">Theses</option>
</select>

<label for="year_from">Year from</label>
<input type="number" id="year_from" name="year_from" placeholder="e.g., 2019">

<label for="year_to">Year to</label>
<input type="number" id="year_to" name="year_to" placeholder="e.g., 2024">

<button type="submit">Search</button>
</form>

{% if query %}
<h2>Query: <em>{{query}}</em></h2>
<h3>AI -> VuFind translated query</h3>
<pre>{{translated}}</pre>

{% if filters %}
<div><strong>Applied facets:</strong>
{% for k,v in filters.items() if v %}
  {{k}} = {{v}}{% if not loop.last %}, {% endif %}
{% endfor %}
</div>
{% endif %}

{% if error %}
<div style="background:#fff3cd; border:1px solid #ffc107; padding:1rem; border-radius:6px; margin:1rem 0;">
  <strong style="color:#856404;">Fehler bei der Suche:</strong>
  <div style="color:#856404; margin-top:0.5rem;">{{error}}</div>
</div>
{% endif %}

<h3>Search results ({{results|length}})</h3>
{% for r in results %}
<div class="result">
  <div><strong>{{r.title}}</strong></div>
  <div class="meta">{{r.authors}} — {{r.year}} — {{r.format}} — <a href="{{r.link}}" target="_blank">Open record</a></div>
  {% if r.snippet %}<div style="margin-top:.5rem">{{r.snippet}}</div>{% endif %}
</div>
{% endfor %}

<h3>AI Summary</h3>
<div class="summ">{{ summary_html }}</div>
{% endif %}
</body>
</html>
"""

# --- Helpers ---


def _safe_url(url):
    """Validate URL to prevent javascript: URIs and other dangerous schemes."""
    if not url:
        return "#"
    parsed = urlparse(url)
    if parsed.scheme.lower() in ("http", "https"):
        return url
    return "#"


def translate_nl_to_vufind(nl_query):
    """
    Convert natural language query to VuFind parameters via OpenAI
    """
    system = (
        "You are an assistant that converts natural-language library search queries "
        "into VuFind API search parameters. Return JSON with keys: 'lookfor' (string), "
        "'type' (optional, any of AllFields, Title, Author, Subject, CallNumber, ISN, tag), "
        "'filters' (dict: language, year_from, year_to, material_type)."
    )
    prompt = f"Convert this user query into VuFind JSON:\n{nl_query}\nReturn only JSON."
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=400,
        temperature=0.0,
        timeout=60,
    )
    text = resp.choices[0].message.content.strip()
    # Strip Markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        return {"lookfor": nl_query}


def call_vufind_search(params):
    """
    Call VuFind REST API with filters.
    Returns dict with 'records' key on success, or dict with 'error' key on failure.
    """
    query_params = {"lookfor": params.get("lookfor", ""), "limit": 10}
    filters = params.get("filters", {})
    query_params["filter[]"] = []
    if "language" in filters and filters["language"]:
        query_params["filter[]"].append(f"language:\"{filters['language']}\"")
    if "material_type" in filters and filters["material_type"]:
        query_params["filter[]"].append(f"type:\"{filters['material_type']}\"")
    if ("year_from" in filters and filters["year_from"]) or (
        "year_to" in filters and filters["year_to"]
    ):
        yf = filters.get("year_from", "")
        yt = filters.get("year_to", "")
        # query_params["filter[]"].append(f"year:\"{yf}-{yt}\"")

    try:
        r = requests.get(VUFIND_SEARCH_ENDPOINT, params=query_params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code == 403:
            msg = (
                "Zugriff verweigert (HTTP 403). "
                "Bitte überprüfen Sie die Konfiguration der VuFind-API-URL und eventuelle "
                "Zugriffsbeschränkungen (IP-Sperre, Authentifizierung)."
            )
        elif status_code == 404:
            msg = (
                "VuFind-Endpoint nicht gefunden (HTTP 404). "
                "Bitte überprüfen Sie die Konfiguration von VUFIND_SEARCH_ENDPOINT."
            )
        elif status_code == 401:
            msg = (
                "Nicht autorisiert (HTTP 401). "
                "Die VuFind-API erfordert eine Authentifizierung. "
                "Bitte überprüfen Sie Ihre Zugangsdaten."
            )
        elif status_code is not None and status_code >= 500:
            msg = (
                f"Serverfehler (HTTP {status_code}) bei der VuFind-API. "
                "Bitte versuchen Sie es später erneut."
            )
        else:
            msg = (
                f"HTTP-Fehler {status_code or ''} bei der Anfrage an die VuFind-API. "
                f"Details: {e}"
            )
        return {"error": msg}
    except requests.exceptions.ConnectionError:
        return {
            "error": (
                "Verbindung zur VuFind-API fehlgeschlagen. "
                "Bitte überprüfen Sie die Netzwerkverbindung und die Konfiguration "
                "von VUFIND_SEARCH_ENDPOINT."
            )
        }
    except requests.exceptions.Timeout:
        return {
            "error": (
                "Zeitüberschreitung bei der Anfrage an die VuFind-API. "
                "Der Server hat zu lange nicht geantwortet. "
                "Bitte versuchen Sie es später erneut."
            )
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Unerwarteter Fehler bei der API-Anfrage: {e}"}


def normalize_vufind_json(raw_json, max_items=10):
    """
    Normalize VuFind API JSON to list of dicts: title, authors, year, format, snippet, link
    """
    results = []
    records = raw_json.get("records", [])
    for rec in records[:max_items]:
        results.append(
            {
                "title": rec.get("title", "No title"),
                "authors": (
                    ", ".join(rec.get("author", []))
                    if isinstance(rec.get("author"), list)
                    else rec.get("author", "")
                ),
                "year": rec.get("date", ""),
                "format": rec.get("format", ""),
                "snippet": rec.get("description", ""),
                "link": _safe_url(rec.get("url", "")),
            }
        )
    return results


def summarize_results(nl_query, items):
    if not items:
        return "No results to summarize."
    text_items = []
    for i, it in enumerate(items, start=1):
        text_items.append(
            f"{i}. {it['title']} — {it['authors']} ({it['year']}) — {it['snippet']}"
        )
    prompt = (
        f"You are a research assistant. The user asked: {nl_query}\n\n"
        "Below are search results from a VuFind catalog. "
        "Provide a concise summary (3-6 sentences), highlight relevant items, "
        "and suggest 2 follow-up search queries.\n\n" + "\n".join(text_items[:10])
    )
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful academic assistant."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1200,
        temperature=0.2,
        timeout=120,
    )
    summary = resp.choices[0].message.content.strip()
    raw_html = markdown.markdown(summary)
    safe_html = nh3.clean(
        raw_html,
        tags=MD_ALLOWED_TAGS,
        attributes=MD_ALLOWED_ATTRIBUTES,
    )
    return Markup(safe_html)


# --- Flask routes ---


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        INDEX_HTML,
        example="Recent articles on climate resilience in urban planning, English, peer-reviewed",
        query=None,
        error=None,
    )


@app.route("/search", methods=["POST"])
def search():
    nl = request.form.get("nl", "").strip()
    if not nl:
        return index()

    # --- User-selected facets ---
    filters = {}
    language = request.form.get("language", "").strip()
    material_type = request.form.get("material_type", "").strip()
    year_from = request.form.get("year_from", "").strip()
    year_to = request.form.get("year_to", "").strip()

    if language:
        filters["language"] = language
    if material_type:
        filters["material_type"] = material_type
    if year_from:
        filters["year_from"] = year_from
    if year_to:
        filters["year_to"] = year_to

    # --- AI translation ---
    translated = translate_nl_to_vufind(nl)
    # Merge user facets (override AI)
    translated_filters = translated.get("filters", {})
    translated_filters.update(filters)
    translated["filters"] = translated_filters

    # --- VuFind search ---
    raw = call_vufind_search(translated)

    error = None
    results = []
    if isinstance(raw, dict) and raw.get("error"):
        error = raw["error"]
        summary_html = ""
    else:
        results = normalize_vufind_json(raw)
        # --- AI summary ---
        summary_html = summarize_results(nl, results)

    return render_template_string(
        INDEX_HTML,
        query=nl,
        translated=json.dumps(translated, indent=2),
        results=results,
        summary_html=summary_html,
        filters=translated_filters,
        error=error,
    )


# --- Run app ---
if __name__ == "__main__":
    app.run(debug=DEBUGMODE, host=HOST, port=PORT)
