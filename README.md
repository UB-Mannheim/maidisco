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

## Configuration

Key environment variables in `.env`:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key for OpenAI-compatible LLM (required) |
| `OPENAI_API_URL` | Base URL for the LLM API (e.g., `http://localhost:11434/v1` for Ollama) |
| `OPENAI_MODEL` | Model name to use (default: `gpt-4`) |
| `VUFIND_SEARCH_ENDPOINT` | VuFind API search endpoint URL |
| `PRIMO_SEARCH_ENDPOINT` | Primo API search endpoint URL |
| `PRIMO_APIKEY` | Primo API key (optional) |
| `PRIMO_SCOPE` | Primo scope parameter |
| `PRIMO_TAB` | Primo tab parameter |
| `PRIMO_VID` | Primo view ID |
| `HOST` | Server host (default: `127.0.0.1`) |
| `PORT` | Server port (default: `5001`) |
| `DEBUGMODE` | Enable Flask debug mode (default: `False`) |
| `MATOMO_URL` | Matomo tracking URL (optional, e.g. `https://analytics.example.com/`) |
| `MATOMO_SITE_ID` | Matomo site ID (optional) |

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
