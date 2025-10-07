#!/usr/bin/env python3

# primo_ai_frontend.py
"""
Flask web app: Natural-language -> Primo search -> summarize results with AI

Files included in this single-file example:
 - primo_ai_frontend.py  (this file)
 - requirements.txt      (listed below)
 - .env (example shown in comments)

Usage:
 1. Install dependencies: pip install -r requirements.txt
 2. Set environment variables (see .env example below)
 3. Run: python primo_ai_frontend.py

Notes / Configuration
 - This is a minimal, opinionated prototype meant to be adapted to your Primo instance.
 - Set PRIMO_SEARCH_ENDPOINT to the Primo REST endpoint that returns JSON (PNX or other JSON).
   If your institution requires API keys, set PRIMO_API_KEY. If the Primo instance uses a cookie/session for auth
   (e.g. Shibboleth), prefer the browser-extension approach or a proxy that attaches the user's session cookie.
 - OPENAI_API_KEY must be set. Optionally set OPENAI_MODEL (default: gpt-4).

Security
 - Never commit your API keys. Use an environment file or a secrets manager in production.
 - TLS (HTTPS) is required in production.

"""

from flask import Flask, render_template_string, request, redirect, url_for, jsonify
import os
import requests
import openai
import json
from urllib.parse import urlencode

from dotenv import load_dotenv
load_dotenv()

# ---------- Configuration (via env vars) ----------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")
PRIMO_SEARCH_ENDPOINT = os.environ.get("PRIMO_SEARCH_ENDPOINT", "https://your-primo-instance.example.com/primo-explore/ws/v1/search")
PRIMO_API_KEY = os.environ.get("PRIMO_API_KEY")  # optional
PRIMO_INSTITUTION = os.environ.get("PRIMO_INSTITUTION")  # optional, e.g. 'MAN'

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")

openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

# ---------- Simple HTML template ----------
INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Primo AI Search Frontend</title>
    <style>
      body { font-family: Arial, Helvetica, sans-serif; margin: 2rem; }
      input[type=text], textarea { width: 100%; padding: 0.5rem; margin-bottom: 0.5rem; }
      .result { border: 1px solid #ddd; padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 6px; }
      .meta { color: #666; font-size: 0.9rem; }
      .summ { background: #f7f7f9; padding: 0.75rem; border-radius: 6px; }
    </style>
  </head>
  <body>
    <h1>Primo AI Search Frontend (Prototype)</h1>
    <form method="post" action="/search">
      <label for="nl">Search (natural language)</label>
      <textarea id="nl" name="nl" rows="3" placeholder="e.g. Recent articles (2019-2024) on climate resilience in urban planning, English, peer-reviewed">{{example}}</textarea>
      <button type="submit">Search</button>
    </form>

    {% if query %}
      <h2>Query: <em>{{query}}</em></h2>

      <h3>AI -> Primo translated query</h3>
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
      <div class="summ">{{summary}}</div>
    {% endif %}

    <hr />
    <p>Prototype — adapt for your Primo instance. See README in code comments for env vars.</p>
  </body>
</html>
"""

# ---------- Helper: call OpenAI to translate NL -> structured Primo query ----------
def translate_nl_to_primo(nl_query):
    """
    Use the LLM to produce a structured query string or parameters that map to Primo's search syntax.
    Output must be JSON like:
      {"q":"...", "filter": {"datetype":"2019-2024","language":"eng","mat_type":"article"}}
    The function returns a dict with at least the key 'q' (string).
    """
    system = (
        "You are an assistant that translates natural-language literature search requests into structured Primo search parameters."
        " Output valid JSON only. Fields: q (string, the core search expression), filters (object with optional keys: year_from, year_to, language, material_type, subject, author, title).")

    prompt = f"Translate this user query into a Primo search JSON:\nUser query:\n{nl_query}\n\nReturn only JSON."

    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400,
        temperature=0.0,
    )

    text = resp['choices'][0]['message']['content'].strip()
    # Try to parse JSON from the model output
    try:
        parsed = json.loads(text)
    except Exception:
        # fallback: ask model to produce a simplified JSON
        return {"q": nl_query}
    return parsed


# ---------- Helper: call Primo search endpoint ----------

def call_primo_search(params):
    """
    Call the configured Primo search endpoint. params should be a dict; we will translate it to querystring.
    This function expects PRIMO_SEARCH_ENDPOINT to accept simple GET requests returning JSON.

    Adapt this for the exact Primo REST you have (PNX, Alma/Primo APIs differ).
    """
    headers = {"Accept": "application/json"}
    if PRIMO_API_KEY:
        headers['Authorization'] = f"apikey {PRIMO_API_KEY}"

    try:
        r = requests.get(PRIMO_SEARCH_ENDPOINT, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "status_code": getattr(e, 'response', None)}


# ---------- Helper: normalize Primo JSON to simple list ----------

def normalize_primo_json(raw_json, max_items=10):
    """
    Convert institution-specific Primo JSON to a list of items with keys: title, authors, year, format, snippet, link
    This function must be adapted to the exact JSON your Primo returns. Here we attempt several common patterns.
    """
    results = []

    # Try common 'docs' or 'records' patterns
    docs = None
    if isinstance(raw_json, dict):
        # common fields
        if 'docs' in raw_json:
            docs = raw_json['docs']
        elif 'records' in raw_json:
            docs = raw_json['records']
        elif 'pnx' in raw_json and isinstance(raw_json['pnx'], list):
            docs = raw_json['pnx']
        elif 'items' in raw_json:
            docs = raw_json['items']

    if not docs:
        # fallback: try to extract top-level list
        if isinstance(raw_json, list):
            docs = raw_json

    if not docs:
        return results

    for doc in docs[:max_items]:
        title = doc.get('title') or doc.get('title_display') or doc.get('recordTitle') or None
        # authors often in 'creator' or 'author'
        authors = None
        if isinstance(doc.get('creator'), list):
            authors = ", ".join(doc.get('creator'))
        else:
            authors = doc.get('creator') or doc.get('author') or None

        year = doc.get('date') or doc.get('year') or None
        fmt = doc.get('type') or doc.get('materialType') or doc.get('format') or None
        snippet = doc.get('snippet') or doc.get('description') or None
        link = doc.get('link') or doc.get('record_link') or doc.get('pnx', {}).get('control', {}).get('recordid') if isinstance(doc, dict) else None

        # If link is a record id only, we leave it as-is; the UI should make it clickable by constructing an openURL if possible.
        results.append({
            'title': title or 'No title',
            'authors': authors or '',
            'year': year or '',
            'format': fmt or '',
            'snippet': snippet or '',
            'link': link or '#'
        })

    return results


# ---------- Helper: summarize results with OpenAI ----------

def summarize_results(nl_query, items):
    """
    Ask the LLM to summarize the returned items, explain relevance, and suggest follow-ups.
    """
    if not items:
        return "No results to summarize."

    text_items = []
    for i, it in enumerate(items, start=1):
        text_items.append(f"{i}. {it['title']} — {it['authors']} ({it['year']}) — {it['snippet']}")

    prompt = (
        f"You are a research assistant. A user asked: {nl_query}\n\n"
        "Below are search results returned from a library catalog. Provide a concise summary (3-6 sentences) that synthesizes the main themes covered by these results, calls out any especially relevant items, and suggests 2 follow-up search suggestions (phrased as natural-language queries) to refine the results.\n\nResults:\n"
        + "\n".join(text_items[:10])
    )

    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful academic research assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400,
        temperature=0.2,
    )

    return resp['choices'][0]['message']['content'].strip()


# ---------- Flask routes ----------

@app.route('/', methods=['GET'])
def index():
    return render_template_string(INDEX_HTML, example="e.g. Recent articles (2019-2024) on climate resilience in urban planning, English, peer-reviewed", query=None)


@app.route('/search', methods=['POST'])
def search():
    nl = request.form.get('nl', '').strip()
    if not nl:
        return redirect(url_for('index'))

    # 1) Translate NL -> Primo params via OpenAI
    translated = translate_nl_to_primo(nl)

    # 2) Convert translated JSON into params for the Primo endpoint
    # The exact mapping will depend on your Primo REST API. We create a simple mapping here.
    params = {}
    q = translated.get('q') if isinstance(translated, dict) else None
    if q:
        params['query'] = q
    # Map common filters
    filters = translated.get('filters', {}) if isinstance(translated, dict) else {}
    if filters.get('year_from') and filters.get('year_to'):
        params['fromYear'] = filters['year_from']
        params['toYear'] = filters['year_to']
    if filters.get('language'):
        params['lang'] = filters['language']
    if filters.get('material_type'):
        params['materialType'] = filters['material_type']

    # Institution param
    if PRIMO_INSTITUTION:
        params['institution'] = PRIMO_INSTITUTION

    # 3) Call Primo
    raw = call_primo_search(params)
    items = []
    if isinstance(raw, dict) and raw.get('error'):
        summary = f"Error calling Primo: {raw.get('error')}"
    else:
        items = normalize_primo_json(raw)
        # 4) Summarize
        summary = summarize_results(nl, items)

    return render_template_string(INDEX_HTML, query=nl, translated=json.dumps(translated, indent=2), results=items, summary=summary)


# ---------- Standalone run ----------
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
