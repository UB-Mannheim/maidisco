import json
import os
import time

import requests
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# Ollama configuration - can be overridden by environment variables
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
OLLAMA_PORT = os.environ.get("OLLAMA_PORT", "11434")
OLLAMA_API_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate"
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "llama3:8b")

print(f"Using Ollama at: {OLLAMA_API_URL}")
print(f"Using model: {MODEL_NAME}")


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

    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}

    start_time = time.time()

    try:
        print(f"Sending request to Ollama: {OLLAMA_API_URL}")
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
        end_time = time.time()
        processing_time = end_time - start_time

        print(f"Ollama response status: {response.status_code}")
        response.raise_for_status()
        result = response.json()

        # Extract and parse JSON from response
        content = result.get("response", "{}")

        # Handle potential markdown code blocks
        if content.strip().startswith("`"):
            lines = content.strip().split("\n")[1:-1]
            content = "\n".join(lines)

        # Try to parse the JSON
        parsed_result = json.loads(content)
        parsed_result["processing_time_seconds"] = round(processing_time, 2)

        return parsed_result
    except requests.exceptions.ConnectionError as e:
        end_time = time.time()
        return {
            "error": "Cannot connect to Ollama",
            "details": f"Make sure Ollama is running and accessible at {OLLAMA_API_URL}",
            "exception": str(e),
            "processing_time_seconds": round(end_time - start_time, 2),
        }
    except requests.exceptions.Timeout:
        end_time = time.time()
        return {
            "error": "Ollama request timeout",
            "details": "The request took too long to process",
            "processing_time_seconds": round(end_time - start_time, 2),
        }
    except requests.exceptions.HTTPError as e:
        end_time = time.time()
        return {
            "error": "Ollama HTTP error",
            "details": f"Status code: {response.status_code}",
            "response": response.text,
            "processing_time_seconds": round(end_time - start_time, 2),
        }
    except json.JSONDecodeError as e:
        end_time = time.time()
        return {
            "error": "Invalid JSON response from Ollama",
            "details": str(e),
            "response": content,
            "processing_time_seconds": round(end_time - start_time, 2),
        }
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
        textarea { width: 100%; height: 100px; padding: 10px; font-family: inherit; }
        button { padding: 10px 20px; background: #4CAF50; color: white; border: none; cursor: pointer; }
        button:hover { background: #45a049; }
        button:disabled { background: #cccccc; cursor: not-allowed; }
        #result { background: #f5f5f5; padding: 15px; border-radius: 5px; white-space: pre-wrap; font-family: monospace; }
        .loading { display: none; color: #666; }
        .error { color: #d32f2f; }
        .success { color: #388e3c; }
        .info { background: #e3f2fd; padding: 10px; border-radius: 5px; }
        .timing { font-size: 0.9em; color: #666; margin-top: 10px; }
        .progress-bar {
            width: 100%;
            background-color: #f0f0f0;
            border-radius: 5px;
            margin: 10px 0;
        }
        .progress-bar-fill {
            height: 20px;
            background-color: #4CAF50;
            border-radius: 5px;
            width: 0%;
            transition: width 0.3s;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Search Query Analyzer</h1>
        <div class="info">
            <strong>Ollama Configuration:</strong><br>
            Host: <span id="ollama-host"></span><br>
            Model: <span id="ollama-model"></span>
        </div>
        <textarea id="query" placeholder="Enter your search query here..."></textarea>
        <button id="analyze-btn" onclick="analyzeQuery()">Analyze Query (Ctrl+Enter)</button>
        <div class="loading" id="loading">
            <div>Processing your request...</div>
            <div class="progress-bar">
                <div class="progress-bar-fill" id="progress-fill"></div>
            </div>
            <div id="progress-text">Initializing...</div>
        </div>
        <div id="result"></div>
    </div>

    <script>
        // Display configuration
        document.getElementById('ollama-host').textContent = "{{ request.url_root.replace('http://', '').replace('/', '') }}:{{ '11434' if ':' not in request.host else request.host.split(':')[1] }}";
        document.getElementById('ollama-model').textContent = "{{ MODEL_NAME }}";
        
        let startTime;
        
        function updateProgress(message, percent) {
            document.getElementById('progress-text').textContent = message;
            document.getElementById('progress-fill').style.width = percent + '%';
        }
        
        async function analyzeQuery() {
            const query = document.getElementById('query').value;
            const resultDiv = document.getElementById('result');
            const loadingDiv = document.getElementById('loading');
            const analyzeBtn = document.getElementById('analyze-btn');
            
            if (!query.trim()) {
                resultDiv.innerHTML = '<div class="error">Please enter a query</div>';
                return;
            }
            
            // Disable button and show loading
            analyzeBtn.disabled = true;
            loadingDiv.style.display = 'block';
            resultDiv.innerHTML = '';
            startTime = new Date();
            
            // Simulate progress
            updateProgress('Connecting to Ollama...', 20);
            
            try {
                updateProgress('Sending request to LLM...', 40);
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query })
                });
                
                updateProgress('Processing response...', 80);
                const data = await response.json();
                
                if (data.error) {
                    resultDiv.innerHTML = `<div class="error"><strong>Error:</strong> ${data.error}<br><small>${data.details || ''}</small></div>`;
                    if (data.response) {
                        resultDiv.innerHTML += `<br><strong>Raw Response:</strong><br><pre>${data.response}</pre>`;
                    }
                    if (data.exception) {
                        resultDiv.innerHTML += `<br><strong>Exception:</strong><br><pre>${data.exception}</pre>`;
                    }
                } else {
                    const endTime = new Date();
                    const totalTime = ((endTime - startTime) / 1000).toFixed(2);
                    resultDiv.innerHTML = `<div class="success">Analysis successful (${totalTime}s):</div><pre>${JSON.stringify(data, null, 2)}</pre>`;
                }
            } catch (error) {
                resultDiv.innerHTML = `<div class="error">Network Error: ${error.message}</div>`;
            } finally {
                updateProgress('Complete', 100);
                loadingDiv.style.display = 'none';
                analyzeBtn.disabled = false;
            }
        }
        
        // Allow Enter+Ctrl to submit
        document.getElementById('query').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && e.ctrlKey) {
                analyzeQuery();
            }
        });
        
        // Focus on textarea on load
        window.onload = function() {
            document.getElementById('query').focus();
        };
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
    print("=" * 50)
    print("Search Query Analyzer")
    print("=" * 50)
    print(f"Ollama Host: {OLLAMA_HOST}")
    print(f"Ollama Port: {OLLAMA_PORT}")
    print(f"Ollama API URL: {OLLAMA_API_URL}")
    print(f"Model: {MODEL_NAME}")
    print("=" * 50)
    print("Make sure Ollama is running and accessible")
    print("Visit http://localhost:5000 in your browser")
    print("=" * 50)

    app.run(debug=True, host="0.0.0.0", port=8008)
