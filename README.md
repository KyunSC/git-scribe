# GitScribe

Automatically generate documentation for your codebase from its git history using LLMs.

GitScribe reads your commit history, analyzes diffs with Claude, and produces changelogs, module documentation, and architecture overviews — so your docs stay in sync with your code without manual effort.

## How It Works

GitScribe uses a three-layer LLM pipeline to turn raw git data into polished documentation:

1. **Diff Analyzer** — Examines each file's changes and classifies them (feature, bugfix, refactor, etc.)
2. **Change Synthesizer** — Groups related file changes into coherent narratives per PR or release
3. **Doc Generator** — Produces specific output formats from the synthesized data

Changes are batched by PR, merge commit, or time window. The pipeline runs incrementally, so only new commits are processed on subsequent runs.

## Output Formats

- **Changelog** — Conventional changelog entries grouped by Added / Changed / Fixed / Breaking
- **Module Docs** — Per-directory documentation covering purpose, public API, dependencies, and recent changes
- **Architecture Overview** — High-level system description with component relationships and coupling analysis

## Tech Stack

- **Python / FastAPI** — Backend and API layer
- **LangGraph** — Orchestrates the multi-step LLM pipeline
- **Claude Sonnet (Anthropic API)** — Powers diff analysis and doc generation
- **PostgreSQL** — Stores processed results, doc versions, and pipeline state
- **GitPython** — Extracts commits, diffs, and repo metadata

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- An [Anthropic API key](https://console.anthropic.com/)

### Installation

```bash
git clone https://github.com/KyunSC/gitscribe.git
cd gitscribe
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your-api-key
DATABASE_URL=postgresql://user:password@localhost:5432/gitscribe
```

### Database Setup

```bash
python -m gitscribe.db.migrate
```

### Usage

**Analyze a local repo:**

```bash
python -m gitscribe run /path/to/your/repo
```

**Analyze with a specific batch strategy:**

```bash
# Group changes by PR/merge commit (default)
python -m gitscribe run /path/to/repo --batch-by pr

# Group changes by tag/release
python -m gitscribe run /path/to/repo --batch-by tag

# Group changes by week
python -m gitscribe run /path/to/repo --batch-by week
```

**Generate specific doc types:**

```bash
# Changelog only
python -m gitscribe run /path/to/repo --output changelog

# Module docs only
python -m gitscribe run /path/to/repo --output modules

# Everything
python -m gitscribe run /path/to/repo --output all
```

**Run incrementally (skip already-processed commits):**

```bash
python -m gitscribe run /path/to/repo --incremental
```

### API Server

```bash
uvicorn gitscribe.api:app --reload
```

| Endpoint | Method | Description |
|---|---|---|
| `/api/repos` | POST | Register a repo for processing |
| `/api/repos/{id}/run` | POST | Trigger a documentation run |
| `/api/repos/{id}/docs` | GET | Retrieve generated documentation |
| `/api/repos/{id}/changelog` | GET | Get the latest changelog |
| `/api/repos/{id}/status` | GET | Check pipeline status |

## Project Structure

```
gitscribe/
├── api/              # FastAPI routes and request models
├── git/              # Git reader and diff extraction
├── pipeline/         # LangGraph pipeline definition
│   ├── layer1.py     # Diff analyzer (per-file)
│   ├── layer2.py     # Change synthesizer (per-batch)
│   └── layer3.py     # Doc generators (changelog, modules, architecture)
├── prompts/          # Versioned LLM prompt templates
├── db/               # PostgreSQL models and migrations
├── output/           # Doc formatters and writers
└── config.py         # Environment and pipeline configuration
```

## Filtering

GitScribe automatically skips noise to save API costs and improve output quality:

- Lockfiles (`package-lock.json`, `yarn.lock`, `poetry.lock`)
- Merge commits with no unique changes
- Auto-generated files (`.pb.go`, timestamp-only migrations)
- Whitespace and formatting-only changes

Custom filters can be added in `gitscribe/git/filters.py`.

## Cost

The pipeline is designed to be cost-efficient. For a typical repo with ~50 PRs/month averaging 10 files each, expect roughly 600 API calls/month, well under $10 with Claude Sonnet.

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Open a pull request

## License

MIT
