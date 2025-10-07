from flask import Flask, render_template_string, request
import os
import requests
import openai
import json
import markdown
from markupsafe import Markup

# Load environment variables if using .env
from dotenv import load_dotenv
load_dotenv()

# Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")
VUFIND_SEARCH_ENDPOINT = os.environ.get(
    "VUFIND_SEARCH_ENDPOINT", "https://your-vufind-instance.example.com/api/search"
)

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")

openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

# Simple template
INDEX_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>VuFind AI Search</title>
<style>
body { font-family: Arial; margin: 2rem; }
input, textarea { width: 100%; padding: 0.5rem; margin-bottom: 0.5rem; }
.result { border: 1px solid #ddd; padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 6px; }
.meta { color: #666; font-size: 0.9rem; }
.summ { background: #f7f7f9; padding: 0.75rem; border-radius: 6px; }
</style>
</head>
<body>
<h1>VuFind AI Search Frontend</h1>
<form method="post" action="/search">
<label for="nl">Search (natural language)</label>
<textarea id="nl" name="nl" rows="3">{{example}}</textarea>
<button type="submit">Search</button>
</form>

{% if query %}
<h2>Query: <em>{{query}}</em></h2>
<h3>AI -> VuFind translated query</h3>
<pre>{{translated}}</pre>

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

def translate_nl_to_vufind(nl_query):
    """
    Convert natural language query to VuFind parameters via OpenAI
    """
    system = (
        "You are an assistant that converts natural-language library search queries "
        "into VuFind API search parameters. Return JSON with keys: 'lookfor' (string), "
        "'type' (optional), 'filters' (dict: language, year_from, year_to, material_type)."
    )
    prompt = f"Convert this user query into VuFind JSON:\n{nl_query}\nReturn only JSON."
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
        max_tokens=400,
        temperature=0.0,
        timeout=60
    )
    text = resp['choices'][0]['message']['content'].strip()
    # strip code fences if present
    import re
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except Exception:
        return {"lookfor": nl_query}

def call_vufind_search(params):
    """
    Call VuFind REST API
    """
    # VuFind accepts GET parameters like 'lookfor', 'type', 'limit', 'filter[]'
    query_params = {"lookfor": params.get("lookfor",""), "limit": 10}
    filters = params.get("filters",{})
    if filters.get("language"):
        query_params["filter[]"] = f"language::{filters['language']}"
    if filters.get("year_from") or filters.get("year_to"):
        yr_from = filters.get("year_from", "")
        yr_to = filters.get("year_to", "")
        query_params["filter[]"] = f"year::{yr_from}-{yr_to}"
    if filters.get("material_type"):
        query_params["filter[]"] = f"type::{filters['material_type']}"
    r = requests.get(VUFIND_SEARCH_ENDPOINT, params=query_params, timeout=15)
    r.raise_for_status()
    return r.json()

def normalize_vufind_json(raw_json, max_items=10):
    """
    Normalize VuFind API JSON to a simple list of dicts
    Each dict: title, authors, year, format, snippet, link
    """
    results = []
    records = raw_json.get("records", [])
    for rec in records[:max_items]:
        results.append({
            "title": rec.get("title","No title"),
            "authors": ", ".join(rec.get("author", [])) if isinstance(rec.get("author"), list) else rec.get("author",""),
            "year": rec.get("date",""),
            "format": rec.get("format",""),
            "snippet": rec.get("description",""),
            "link": rec.get("url","#")
        })
    return results

def summarize_results(nl_query, items):
    if not items:
        return "No results to summarize."
    text_items = []
    for i, it in enumerate(items, start=1):
        text_items.append(f"{i}. {it['title']} — {it['authors']} ({it['year']}) — {it['snippet']}")
    prompt = (
        f"You are a research assistant. The user asked: {nl_query}\n\n"
        "Below are search results from a VuFind catalog. "
        "Provide a concise summary (3-6 sentences), highlight relevant items, "
        "and suggest 2 follow-up search queries.\n\n" +
        "\n".join(text_items[:10])
    )
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[{"role":"system","content":"You are a helpful academic assistant."},
                  {"role":"user","content":prompt}],
        max_tokens=1200,
        temperature=0.2,
        timeout=120
    )
    summary = resp['choices'][0]['message']['content'].strip()
    return Markup(markdown.markdown(summary))

# --- Flask routes ---

@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML, example="Recent articles on climate resilience in urban planning, English, peer-reviewed", query=None)

@app.route("/search", methods=["POST"])
def search():
    nl = request.form.get("nl","").strip()
    if not nl:
        return index()
    translated = translate_nl_to_vufind(nl)
    raw = call_vufind_search(translated)
    results = normalize_vufind_json(raw)
    summary_html = summarize_results(nl, results)
    return render_template_string(INDEX_HTML, query=nl, translated=json.dumps(translated, indent=2), results=results, summary_html=summary_html)

# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5001)
