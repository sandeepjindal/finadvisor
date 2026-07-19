# Technology Stack: Personal Financial Advisor (fin-advisor)

## Core Language & Runtime
- **Runtime**: Python >=3.11
- **Package & Virtual Environment Manager**: `uv` (standardizing configuration via `pyproject.toml` and lock files via `uv.lock`)

## Interfaces & Presentation Layer
- **Discord Bot**: Built using `discord.py` (>=2.3) for rich chat interactions and proactive notifications.
- **Local CLI**: Terminal-based chat interface (`scripts/chat.py`) for offline reasoning and testing.

## Orchestration & Storage
- **Database**: Local SQLite database (`brain.db`) for caching queries, maintaining watchlists, storing portfolio holdings, tracking signals, and persisting recommended decisions.
- **Task Scheduling**: `apscheduler` (>=3.10) to run background data synchronization, portfolio move monitoring, and morning digest scheduling.

## Data Providers & Analytical Engines
- **Market Data**: `yfinance` (quotes, fundamentals, valuation, ownership, and options chain).
- **Technical Analysis**: `ta` library (MACD, RSI, golden/death cross, ATR metrics).
- **Data Engineering**: `pandas` and `numpy` for data manipulation, portfolio concentration, beta analysis, and correlation logic.
- **News & Search**: RSS parsing (`feedparser`), web search (`ddgs`), and page extraction (`trafilatura`).
- **Sentiment Scoring**: `vaderSentiment` for simple textual sentiment (with optional extensions like FinBERT using `transformers` + `torch`).
- **Document Ingestion**: `pypdf` for parsing PDF files uploaded to local repository directories.
- **Macroeconomics**: FRED API client (`fredapi`).

## Development & Quality Assurance
- **Testing**: `pytest` and `pytest-asyncio` for executing offline mock tests and running full end-to-end scenarios.
