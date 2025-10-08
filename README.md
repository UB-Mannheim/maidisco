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

Then, start one or both of the provided web applications:

```shell
# Run web application for Primo search with AI support.
./primo_ai_frontend_flask.py

# Run web application for VuFind search with AI support.
```

## Usage

Connect to the running web application in your browser.

- URL for Primo search: http://localhost:5555/
- URL for VuFind search: http://localhost:5001/

## Notice

This is an experimental proof of concept.
It is not intended for production use.
Many features are missing, and the software may have bugs and security issues.

## License

maidisco – Mannheim Intelligent Discovery System for AI assisted search

Copyright (C) 2025 Universitätsbibliothek Mannheim

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
