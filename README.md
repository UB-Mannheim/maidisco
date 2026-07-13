# maidisco
The Mannheim Intelligent Discovery System is an experimental web application
that adds AI assisted search to discovery systems like Primo or VuFind®.

## Installation

The installation is based on macOS, Linux, WSL, or a similar host system
with Git and a sufficiently recent Python3.

Clone this repository and run these commands in your local working directory:

```shell
# Install required software.
python3 -m venv venv
source venv/bin/activate
pip install -U pip -r requirements.txt
```

Copy the file `sample.env` to `.env` and provide your local settings
in the `.env` file.

Then, start the web application:

```shell
# Run web application (supports both VuFind and Primo).
./app.py
```

## Usage

Connect to the running web application in your browser:

- URL: http://localhost:5001/

The application automatically detects which discovery system to use:

- **VuFind** is used by default if `VUFIND_SEARCH_ENDPOINT` is configured
- **Primo** is used if `PRIMO_SEARCH_ENDPOINT` is configured and VuFind is not
- **Primo** can be forced by including "primo" (case-insensitive) in the search query

## API

A JSON API is available for programmatic access (e.g. phone applications).

### `POST /api/search`

Send a natural language query and receive a summary, follow-up suggestions, and results.

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Natural language search query |
| `model` | string | no | LLM model name (defaults to first in `LLM_MODELS`) |

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Plain text summary of the search results |
| `follow_up_queries` | string[] | Suggested follow-up questions |
| `results` | object[] | Matching records (title, author, url, year) |

**Rate limiting:** 10 requests per minute per IP (configurable via `API_RATE_LIMIT`).

**Example**

```bash
curl -s -X POST http://127.0.0.1:5001/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Bücher über Künstliche Intelligenz"}' | python3 -m json.tool
```

```json
{
  "follow_up_queries": [
    "Gibt es Neuerscheinungen zu diesem Thema?"
  ],
  "results": [
    {
      "author": "Stuart Russell",
      "title": "Artificial Intelligence: A Modern Approach",
      "url": "https://example.com/...",
      "year": "2021"
    }
  ],
  "summary": "Es wurden 3 Treffer gefunden. Das bekannteste Werk ist ..."
}
```

**Error responses** use appropriate HTTP status codes (400, 429, 502, 503) with a JSON body `{"error": "..."}`.

## Deployment with systemd

For running as a system service (Linux), a systemd unit file is included.

```shell
# Create system user
sudo useradd -r -s /sbin/nologin ai

# Deploy application
sudo mkdir -p /opt/maidisco
sudo cp -r . /opt/maidisco/
sudo chown -R ai:ai /opt/maidisco

# Set up virtual environment
sudo -u ai python3 -m venv /opt/maidisco/venv
sudo -u ai /opt/maidisco/venv/bin/pip install -U pip -r /opt/maidisco/requirements.txt

# Configure
sudo -u ai cp /opt/maidisco/sample.env /opt/maidisco/.env
sudo nano /opt/maidisco/.env   # edit settings

# Install and start service
sudo cp /opt/maidisco/maidisco.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now maidisco
```

To serve under a subpath (e.g. `/maidisco`), set `APPLICATION_ROOT=/maidisco` in `.env`
and configure the WSGI server accordingly. For gunicorn, the systemd service already
passes `SCRIPT_NAME=/maidisco`. An Apache reverse proxy configuration:

```apache
ProxyPass /maidisco/ http://127.0.0.1:5001/
ProxyPassReverse /maidisco/ http://127.0.0.1:5001/
```

## Configuration

Key environment variables in `.env`:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key for OpenAI-compatible LLM (required) |
| `OPENAI_API_URL` | Base URL for the LLM API (e.g., `http://localhost:11434/v1` for Ollama) |
| `LLM_MODELS` | Comma-separated list of available models (first is default, e.g. `gpt-4,llama3,mistral`) |
| `VUFIND_SEARCH_ENDPOINT` | VuFind API search endpoint URL |
| `PRIMO_SEARCH_ENDPOINT` | Primo API search endpoint URL |
| `PRIMO_APIKEY` | Primo API key (optional) |
| `PRIMO_SCOPE` | Primo scope parameter |
| `PRIMO_TAB` | Primo tab parameter |
| `PRIMO_VID` | Primo view ID |
| `HOST` | Server host (default: `127.0.0.1`) |
| `PORT` | Server port (default: `5001`) |
| `APPLICATION_ROOT` | URL prefix for subpath deployment (default: `/`) |
| `MAX_RESULTS` | Maximum number of search results (default: `10`) |
| `API_RATE_LIMIT` | API rate limit: requests per minute per IP (default: `10`) |
| `DEBUGMODE` | Enable Flask debug mode (default: `False`) |
| `MATOMO_URL` | Matomo tracking URL (optional, e.g. `https://analytics.example.com/`) |
| `MATOMO_SITE_ID` | Matomo site ID (optional) |
| `LEGAL_NOTICE_URL` | URL to legal notice/Impressum page (optional) |
| `PRIVACY_URL` | URL to privacy policy/Datenschutz page (optional) |
| `ACCESSIBILITY_URL` | URL to accessibility statement/Barrierefreiheit page (optional) |
| `SIGN_LANGUAGE_URL` | URL to sign language/Gebärdensprache page (optional) |
| `EASY_LANGUAGE_URL` | URL to easy language/Leichte Sprache page (optional) |

## Security

- CSRF protection via Sec-Fetch-Site header validation
- Rate limiting: 30 POST requests per minute per IP
- HTML sanitization in LLM summaries (XSS prevention)
- URL validation (blocks `javascript:` and other dangerous schemes)
- SSRF prevention (validates endpoint URLs at startup)
- Structured LLM prompts to mitigate prompt injection attacks

## Notice

This is an experimental proof of concept.
It is not intended for production use.
Many features are missing, and the software may have bugs and security issues.

## License

maidisco – Mannheim Intelligent Discovery System for AI assisted search

Copyright (C) 2025–2026 Universitätsbibliothek Mannheim

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
