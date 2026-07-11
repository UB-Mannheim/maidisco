#! /usr/bin/env python3

import os
import time

import requests
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# Ollama configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "llama3:8b")


def analyze_search_query(query):
    prompt = f"""
    Analyze the following German search query and provide structured search guidance in JSON format:

    Query: "{query}"

    Return a JSON object with this exact structure:
    {{
      "sources": ["list of relevant information sources"],
      "search_terms": {{
        "german": ["German search terms"],
        "english": ["English search terms"]
      }},
      "facets": ["list of relevant search facets"]
    }}

    Information sources examples:
    - library catalogue
    - web site
    - blog
    - fulltext index of historic prints and handwritings
    - university biography with articles, papers, and other publications

    Search facets examples:
    - author(s)
    - date range
    - language
    - book, journal, article, ...
    - subject
    - publisher
    - location
    - format
    - genre

    Respond ONLY with the valid JSON object. No explanations.
    """

    start_time = time.time()

    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}

    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        result = response.json()

        # Extract and parse JSON from response
        content = result.get("response", "{}")
        # Handle potential markdown code blocks
        if content.startswith("`"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("\n", 1)[0]

        end_time = time.time()
        import json

        parsed_result = json.loads(content)
        parsed_result["processing_time_seconds"] = round(end_time - start_time, 2)
        return parsed_result
    except Exception as e:
        end_time = time.time()
        return {
            "error": "Analysis failed",
            "details": str(e),
            "processing_time_seconds": round(end_time - start_time, 2),
        }


@app.route("/", methods=["GET"])
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Search Query Analyzer</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .container { display: flex; flex-direction: column; gap: 20px; }
        textarea { width: 100%; height: 100px; padding: 10px; }
        button { padding: 10px 20px; background: #4CAF50; color: white; border: none; cursor: pointer; }
        button:hover { background: #45a049; }
        #result { background: #f5f5f5; padding: 15px; border-radius: 5px; white-space: pre-wrap; }
        .loading { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Search Query Analyzer</h1>
        <textarea id="query" placeholder="Enter your search query here..."></textarea>
        <button onclick="analyzeQuery()">Analyze Query</button>
        <div class="loading" id="loading">Analyzing...</div>
        <div id="result"></div>
    </div>

    <script>
        async function analyzeQuery() {
            const query = document.getElementById('query').value;
            const resultDiv = document.getElementById('result');
            const loadingDiv = document.getElementById('loading');

            if (!query.trim()) {
                resultDiv.textContent = "Please enter a query";
                return;
            }

            loadingDiv.style.display = 'block';
            resultDiv.textContent = '';

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query })
                });

                const data = await response.json();
                resultDiv.textContent = JSON.stringify(data, null, 2);
            } catch (error) {
                resultDiv.textContent = "Error: " + error.message;
            } finally {
                loadingDiv.style.display = 'none';
            }
        }

        // Allow Enter+Ctrl to submit
        document.getElementById('query').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && e.ctrlKey) {
                analyzeQuery();
            }
        });
    </script>
</body>
</html>
""")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    query = data.get("query", "")

    if not query:
        return jsonify({"error": "No query provided"}), 400

    result = analyze_search_query(query)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8008)
