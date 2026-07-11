#!/usr/bin/env python3

"""
maidisco — Mannheim Intelligent Discovery System

AI-powered library search frontend supporting VuFind and Primo.

Usage:
  1. Install dependencies: pip install -r requirements.txt
  2. Copy sample.env to .env and configure your endpoints
  3. Run: python app.py

System detection:
  - If "primo" appears in the search query (case-insensitive), use Primo
  - Otherwise, use VuFind if VUFIND_SEARCH_ENDPOINT is configured
  - Fall back to Primo if PRIMO_SEARCH_ENDPOINT is configured
"""

import json
import os
import re
import time
import warnings
from collections import defaultdict
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, abort, render_template, request
from openai import OpenAI

from systems import PrimoSystem, VuFindSystem

load_dotenv()

# --- Configuration ---
DEBUGMODE = os.environ.get("DEBUGMODE", False)
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5001"))

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_API_URL = os.environ.get("OPENAI_API_URL")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")

VUFIND_SEARCH_ENDPOINT = os.environ.get("VUFIND_SEARCH_ENDPOINT")
PRIMO_SEARCH_ENDPOINT = os.environ.get("PRIMO_SEARCH_ENDPOINT")

MATOMO_URL = os.environ.get("MATOMO_URL")
MATOMO_SITE_ID = os.environ.get("MATOMO_SITE_ID")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")


# --- SSRF Prevention ---
def _validate_endpoint(url, name):
    """Validate endpoint URL to prevent SSRF attacks."""
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise RuntimeError(f"{name} must use http or https scheme")
    if parsed.scheme == "http":
        warnings.warn(f"{name} uses HTTP instead of HTTPS — not recommended for production")
    hostname = parsed.hostname or ""
    private_prefixes = (
        "127.", "10.", "192.168.",
        "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
        "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "0.", "169.254.",
    )
    if hostname == "localhost" or any(hostname.startswith(p) for p in private_prefixes):
        warnings.warn(f"{name} points to a private/local address — intended for development only")


if VUFIND_SEARCH_ENDPOINT:
    _validate_endpoint(VUFIND_SEARCH_ENDPOINT, "VUFIND_SEARCH_ENDPOINT")
if PRIMO_SEARCH_ENDPOINT:
    _validate_endpoint(PRIMO_SEARCH_ENDPOINT, "PRIMO_SEARCH_ENDPOINT")


# --- Initialize OpenAI client and discovery systems ---
client = OpenAI(base_url=OPENAI_API_URL, api_key=OPENAI_API_KEY)

systems = {}
if VUFIND_SEARCH_ENDPOINT:
    systems["vufind"] = VuFindSystem(client, OPENAI_MODEL)
if PRIMO_SEARCH_ENDPOINT:
    systems["primo"] = PrimoSystem(client, OPENAI_MODEL)

if not systems:
    raise RuntimeError(
        "No discovery system configured. "
        "Set VUFIND_SEARCH_ENDPOINT or PRIMO_SEARCH_ENDPOINT in .env"
    )

app = Flask(__name__)

APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/")
app.config["APPLICATION_ROOT"] = APPLICATION_ROOT


# --- WSGI Middleware for subpath deployment ---
class _ScriptNameMiddleware:
    """Set SCRIPT_NAME so url_for() generates correct URLs under a subpath."""

    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.prefix
        return self.wsgi_app(environ, start_response)


if APPLICATION_ROOT != "/":
    app.wsgi_app = _ScriptNameMiddleware(app.wsgi_app, APPLICATION_ROOT)


# --- CSRF Protection ---
@app.before_request
def csrf_check():
    """Validate Sec-Fetch-Site header to prevent CSRF attacks."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("Origin")
    site = request.headers.get("Sec-Fetch-Site", "")
    if site in ("same-origin", "none"):
        return
    if not site and not origin:
        return
    if origin:
        origin_host = urlparse(origin).hostname
        if origin_host == request.host:
            return
    abort(403, "CSRF-Validierung fehlgeschlagen")


# --- Rate Limiting ---
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW = 60
_rate_limit_data = defaultdict(list)


@app.before_request
def rate_limit_check():
    """Simple in-memory rate limiter per IP address."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    client_ip = request.remote_addr or "unknown"
    now = time.time()
    _rate_limit_data[client_ip] = [
        t for t in _rate_limit_data[client_ip] if now - t < RATE_LIMIT_WINDOW
    ]
    if len(_rate_limit_data[client_ip]) >= RATE_LIMIT_REQUESTS:
        abort(429, "Zu viele Anfragen. Bitte warten Sie einen Moment.")
    _rate_limit_data[client_ip].append(now)


# --- System Detection ---
def detect_system(nl_query):
    """
    Determine which discovery system to use.

    Priority:
    1. If "primo" appears in query and Primo is configured, use Primo
    2. Use VuFind if configured (default)
    3. Fall back to Primo if configured
    """
    # Check if explicitly requested
    if re.search(r"primo", nl_query, re.IGNORECASE):
        if "primo" in systems:
            return systems["primo"]
        # Primo not configured, fall through to default

    # Default: VuFind if available
    if "vufind" in systems:
        return systems["vufind"]

    # Fallback: Primo if available
    if "primo" in systems:
        return systems["primo"]

    return None


# --- Flask Routes ---
@app.route("/", methods=["GET"])
def index():
    system_name = None
    format_facets = []
    if "vufind" in systems:
        system_name = "VuFind"
        format_facets = systems["vufind"].get_format_facets()
    elif "primo" in systems:
        system_name = "Primo"

    return render_template(
        "index.html",
        example="Recent articles on climate resilience in urban planning, English, peer-reviewed",
        query=None,
        error=None,
        system_name=system_name,
        show_filters="vufind" in systems,
        format_facets=format_facets,
        matomo_url=MATOMO_URL,
        matomo_site_id=MATOMO_SITE_ID,
    )


@app.route("/search", methods=["POST"])
def search():
    nl = request.form.get("nl", "").strip()
    if not nl:
        return index()

    # Detect system
    system = detect_system(nl)
    if not system:
        return render_template(
            "index.html",
            query=nl,
            error="Kein Discovery-System konfiguriert.",
            system_name=None,
            show_filters=False,
            format_facets=[],
            matomo_url=MATOMO_URL,
            matomo_site_id=MATOMO_SITE_ID,
        )

    # Collect user filters (for systems that support them)
    user_filters = {}
    if system.name == "vufind":
        language = request.form.get("language", "").strip()
        material_type = request.form.get("material_type", "").strip()
        year_from = request.form.get("year_from", "").strip()
        year_to = request.form.get("year_to", "").strip()
        if language:
            user_filters["language"] = language
        if material_type:
            user_filters["material_type"] = material_type
        if year_from:
            user_filters["year_from"] = year_from
        if year_to:
            user_filters["year_to"] = year_to

    # Translate query
    try:
        translated = system.translate_query(nl)
    except Exception as e:
        return render_template(
            "index.html",
            query=nl,
            error=str(e),
            system_name=system.name.upper(),
            show_filters=system.name == "vufind",
            matomo_url=MATOMO_URL,
            matomo_site_id=MATOMO_SITE_ID,
        )

    # Build search parameters
    params = system.build_search_params(translated, user_filters)

    # Call search
    raw = system.call_search(params)

    # Process results
    error = None
    results = []
    summary_html = ""
    follow_up_queries = []
    filters = {}

    if isinstance(raw, dict) and raw.get("error"):
        error = raw["error"]
    else:
        results = system.normalize_results(raw)
        summary_html, follow_up_queries = system.summarize_results(nl, results)
        if system.name == "vufind":
            filters = params.get("filters", {})

    format_facets = []
    if system.name == "vufind":
        format_facets = system.get_format_facets()

    return render_template(
        "index.html",
        query=nl,
        translated=json.dumps(translated, indent=2),
        results=results,
        summary_html=summary_html,
        follow_up_queries=follow_up_queries,
        filters=filters,
        error=error,
        system_name=system.name.upper(),
        show_filters=system.name == "vufind",
        format_facets=format_facets,
        matomo_url=MATOMO_URL,
        matomo_site_id=MATOMO_SITE_ID,
    )


# --- Run app ---
if __name__ == "__main__":
    print("=" * 50)
    print("maidisco — Mannheim Intelligent Discovery System")
    print("=" * 50)
    print(f"Configured systems: {', '.join(systems.keys())}")
    print(f"Model: {OPENAI_MODEL}")
    print(f"URL: http://{HOST}:{PORT}/")
    print("=" * 50)
    app.run(debug=DEBUGMODE, host=HOST, port=PORT)
