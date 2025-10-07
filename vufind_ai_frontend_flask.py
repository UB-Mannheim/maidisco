#!/usr/bin/env python3

from flask import Flask, render_template_string, request
import os
import requests
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)
import json
import markdown
from markupsafe import Markup
from dotenv import load_dotenv
import re

load_dotenv()

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")
VUFIND_SEARCH_ENDPOINT = os.environ.get(
    "VUFIND_SEARCH_ENDPOINT", "https://your-vufind-instance.example.com/api/search"
)

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")


app = Flask(__name__)

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
    resp = client.chat.completions.create(model=OPENAI_MODEL,
    messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
    max_tokens=400,
    temperature=0.0,
    timeout=60)
    text = resp.choices[0].message.content.strip()
    # Strip Markdown code fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except Exception:
        return {"lookfor": nl_query}

def call_vufind_search(params):
    """
    Call VuFind REST API with filters
    """
    query_params = {"lookfor": params.get("lookfor",""), "limit": 10}
    filters = params.get("filters", {})
    query_params["filter[]"] = []
    if "language" in filters and filters["language"]:
        query_params["filter[]"].append(f"language::{filters['language']}")
    if "material_type" in filters and filters["material_type"]:
        query_params["filter[]"].append(f"type::{filters['material_type']}")
    if ("year_from" in filters and filters["year_from"]) or ("year_to" in filters and filters["year_to"]):
        yf = filters.get("year_from","")
        yt = filters.get("year_to","")
        query_params["filter[]"].append(f"year::{yf}-{yt}")
    r = requests.get(VUFIND_SEARCH_ENDPOINT, params=query_params, timeout=15)
    r.raise_for_status()
    return r.json()

def normalize_vufind_json(raw_json, max_items=10):
    """
    Normalize VuFind API JSON to list of dicts: title, authors, year, format, snippet, link
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
    resp = client.chat.completions.create(model=OPENAI_MODEL,
    messages=[{"role":"system","content":"You are a helpful academic assistant."},
              {"role":"user","content":prompt}],
    max_tokens=1200,
    temperature=0.2,
    timeout=120)
    summary = resp.choices[0].message.content.strip()
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

    # --- User-selected facets ---
    filters = {}
    language = request.form.get("language","").strip()
    material_type = request.form.get("material_type","").strip()
    year_from = request.form.get("year_from","").strip()
    year_to = request.form.get("year_to","").strip()
    if language: filters["language"] = language
    if material_type: filters["material_type"] = material_type
    if year_from: filters["year_from"] = year_from
    if year_to: filters["year_to"] = year_to

    # --- AI translation ---
    translated = translate_nl_to_vufind(nl)
    # Merge user facets (override AI)
    translated_filters = translated.get("filters", {})
    translated_filters.update(filters)
    translated["filters"] = translated_filters

    # --- VuFind search ---
    raw = call_vufind_search(translated)
    results = normalize_vufind_json(raw)

    # --- AI summary ---
    summary_html = summarize_results(nl, results)

    return render_template_string(
        INDEX_HTML,
        query=nl,
        translated=json.dumps(translated, indent=2),
        results=results,
        summary_html=summary_html,
        filters=translated_filters
    )

# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5001)
