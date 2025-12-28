# PhD Advisor Analyzer Agent

Automated research pipeline for evaluating PhD advisor fit from a single faculty profile URL. It extracts profile data, gathers recent papers, checks recruiting statements, and produces a scored markdown report based on your research interests.

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
git clone https://github.com/yourusername/phd-advisor-analyzer-agent.git
cd phd-advisor-analyzer-agent
uv sync
```

### Configure secrets
```bash
cp .env.example .env
# Fill in OPENROUTER_API_KEY, GOOGLE_SEARCH_API_KEY,
# GOOGLE_SEARCH_ENGINE_ID, GOOGLE_AI_STUDIO_API_KEY
```

### Create your Research Interests document

The agent evaluates professors based on YOUR specific research interests and preferences. You need to create a document that describes:
- Your research interests, methods, and background
- What you're looking for in a PhD advisor
- Your preferred advising style and lab environment

See the [Creating Your Research Interests Document](#creating-your-research-interests-document) section below for detailed guidance.

**Quick start:**
```bash
cp example-research-interests.md my-research-interests.md
# Edit my-research-interests.md with your information
```

### Update config
```toml
[runtime]
research_interests_path = "my-research-interests.md"
```

## Configuration
`config.toml` defines runtime paths and model settings.

Key sections:
- `[runtime]`: `research_interests_path` is required. Other fields are reserved for future use.
- `[models.*]`: model name, temperature, max output tokens, and `instructions_path` for each agent.

Instruction files live in `src/instructions/` and are loaded at runtime via `instructions_path`.

## Usage
```bash
# Research a single professor from a faculty profile page
uv run python -m src.main "https://example.edu/faculty/john-smith"

# Skip Gemini paper reviews (faster debug, no AI Studio key needed)
uv run python -m src.main --debug-skip-reviews "https://example.edu/faculty/john-smith"
```

The tool works with most university faculty profile pages. Simply provide the URL to the professor's profile page.

For CLI help:
```bash
uv run python -m src.main --help
```

## Output
Reports are saved to `reports/` with names like:
```
85_John_Smith.md
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
3. Downselector agent ranks papers by relevance to your research interests and summarizes PDFs with Gemini.
4. Recruiting agent finds verbatim recruiting statements.
5. Main agent synthesizes the final research report based on your research interests.
6. Report formatter writes the markdown file to `reports/`.

## Creating Your Research Interests Document

The agent evaluates professors based on a document that describes **your** research interests, preferred methods, and advising preferences. This is different from a standard Statement of Purpose - it should focus on helping the AI understand what matters to you in a PhD advisor.

### What to Include

Your research interests document should cover:
- **Research goals:** Primary research area and specific topics you want to explore
- **Methods and approaches:** Technical methods, algorithms, and research methodologies you want to work with
- **Background and experience:** Your relevant background and previous research experience
- **Key inspirations:** Papers or researchers that inspire your research direction (optional)
- **Advisor preferences:** What you're looking for in a PhD advisor and lab environment (optional)

### How to Create Your Document

We recommend using an AI assistant to help you create a comprehensive document:

1. **Gather your materials:** Collect any existing documents representing your research interests (Statement of Purpose, research biographies, personal statements, etc.)

2. **Use an AI interview process:** Upload your materials to Claude, ChatGPT, or another frontier model and have it interview you with follow-up questions

3. **Example prompt to start:**
   ```
   I'm applying to PhD programs and need help creating a "Research Interests" document
   that will be used by an AI agent to evaluate whether professors would be good advisor
   fits for me.

   I've attached my Statement of Purpose and [other relevant documents]. Please interview
   me in a conversational style with follow-up questions to help me create a comprehensive
   Research Interests document.

   The document should cover:
   - My primary research interests and specific topics I want to explore
   - Technical methods, algorithms, and research methodologies I want to work with
   - My relevant background and experience
   - Papers or researchers that inspire my work (if applicable)
   - What I'm looking for in a PhD advisor and lab environment

   Please ask me questions one at a time, dig deeper based on my responses, and then
   help me compile everything into a well-structured markdown document. The goal is to
   clearly articulate what I want to research and what matters to me in an advisor.
   ```

4. **Review and edit:** Read the AI-generated document carefully and edit it to ensure accuracy

5. **Save and configure:** Save the result as markdown (.md), text (.txt), or PDF (.pdf) and update your `config.toml` to point to it

### Document Template

See `example-research-interests.md` for a complete template with the following sections:

- **Research Interests:** Describe your primary research area and specific topics
- **Methods and Approaches:** List technical methods and research methodologies
- **Background and Experience:** Your relevant background and previous research
- **Key Papers or Inspirations:** Papers or researchers that inspire your work (optional)
- **What You're Looking For in an Advisor:** Advising style and lab environment preferences (optional)

### Evaluation Criteria

The agent uses your document to score professors across these categories:
1. **Research Alignment:** How well does their work match your interests?
2. **Methods Overlap:** Do they use the techniques you want to learn?
3. **Trajectory & Venues:** Are they publishing recently in quality venues?
4. **Advising Capacity:** Are they taking students?
5. **Lab Environment:** What's the lab culture and student outcomes?
6. **Funding:** Do they have active grants?
7. **Program Fit:** Is their department/program the right fit?

**The more specific you are in your document, the better the agent can evaluate fit.**

## Development
```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## License
MIT License. See `LICENSE`.
