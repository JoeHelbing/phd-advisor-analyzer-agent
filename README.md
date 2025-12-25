# Professor Research System

Automated research pipeline for evaluating PhD advisor fit from a single faculty profile URL. It extracts profile data, gathers recent papers, checks recruiting statements, and produces a scored markdown report based on your SOP (statement of purpose).

## Features
- Multi-agent pipeline built on PydanticAI and OpenRouter models
- Faculty profile extraction with structured links and research areas
- Google Scholar scraping with rate pacing and PDF discovery
- Gemini URL Context summaries for selected papers
- Verbatim recruiting quotes with confidence scoring
- Markdown report output and detailed logs

## Quick Start

### Prerequisites
- Python 3.12+
- uv package manager
- API keys:
  - OpenRouter (LLM access)
  - Google Custom Search (web search)
  - Google AI Studio (Gemini URL Context)

### Installation
```bash
git clone https://github.com/yourusername/professor-research.git
cd professor-research
uv sync
```

### Configure secrets
```bash
cp .env.example .env
# Fill in OPENROUTER_API_KEY, GOOGLE_SEARCH_API_KEY,
# GOOGLE_SEARCH_ENGINE_ID, GOOGLE_AI_STUDIO_API_KEY
```

### Create your SOP
```bash
cp example-sop.md my-sop.md
# Edit my-sop.md with your research interests
```

### Update config
```toml
[runtime]
sop_path = "my-sop.md"
```

## Configuration
`config.toml` defines runtime paths and model settings.

Key sections:
- `[runtime]`: `sop_path` is required. Other fields are reserved for future use.
- `[models.*]`: model name, temperature, max output tokens, and `instructions_path` for each agent.

Instruction files live in `src/instructions/` and are loaded at runtime via `instructions_path`.

## Usage
```bash
# Research a single professor from a faculty profile page
uv run python -m src.main "https://profiles.stanford.edu/yejin-choi"

# Skip Gemini paper reviews (faster debug, no AI Studio key needed)
uv run python -m src.main --debug-skip-reviews "https://profiles.stanford.edu/yejin-choi"
```

For CLI help:
```bash
uv run python -m src.main --help
```

## Output
Reports are saved to `reports/` with names like:
```
85_Jane_Doe.md
```
Each report includes:
- Overall score and verdict
- Research fit analysis
- Recruiting status (verbatim quote + source)
- Optional paper reviews (if PDFs were summarized)

Logs are written to:
- `logs/research.log` (project logs)
- `logs/third_party.log` (httpx/openai/crawl4ai)

## How It Works
1. Faculty extractor agent parses the faculty page (and personal homepage if found).
2. Google Scholar scraping collects recent papers with PDF links.
3. Downselector agent ranks papers by SOP relevance and summarizes PDFs with Gemini.
4. Recruiting agent finds verbatim recruiting statements.
5. Main agent synthesizes the final research report.
6. Report formatter writes the markdown file to `reports/`.

## Development
```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## License
MIT License. See `LICENSE`.
