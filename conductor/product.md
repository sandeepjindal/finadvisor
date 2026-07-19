# Product Definition: Personal Financial Advisor (fin-advisor)

## Vision
A standalone, open-source, model-independent AI personal financial advisor agent that operates over Discord and local CLI/Terminal. The agent acts as an advisory-only assistant (with no trading or execution capabilities) for retail investors seeking data-grounded, medium-to-long term investment insights.

## Core Features
1. **Core Thesis Engine & Long-Term Valuation Modeling (`build_thesis`)**:
   - Generates comprehensive BUY/HOLD/WATCH/SELL recommendations.
   - Evaluates multi-timeframe trends, valuation context, fundamentals, analyst ratings, and insider/ownership activity.
   - Outputs a bear/base/bull target range and confidence level calibrated against its own historical track record.
2. **Exit Advisor & Capital Redeployment (`assess_exit`)**:
   - Advises on holding, trimming, or selling positions.
   - Dynamically calculates ATR trailing stops and tightens exits in response to social hype spikes.
   - Identifies capital redeployment opportunities.
3. **Data Grounding & Verification**:
   - Programmatically validates LLM-reported figures against real-time data provider outputs to prevent hallucinations.
   - Grounded reasoning using Yahoo Finance, news RSS feeds, search APIs, SEC filings, and FRED macroeconomics.
4. **Learning Brain**:
   - Persists all past recommendations and market state snapshots in a local SQLite database (`brain.db`).
   - Scores past recommendations against realized performance to continuously adjust advice confidence.

## Non-Goals
- **No Brokerage/Bank Access**: The agent cannot authenticate to financial institutions or access real funds.
- **No Trade Execution**: The agent cannot place buy/sell orders or execute options/futures contracts.
- **No Direct Financial Responsibility**: Recommendations are strictly educational and advisory in nature.

## Target Audience
Retail investors looking for analytical, data-grounded, medium-to-long term investment theses rather than speculative day trading or automated execution.

## Communication Channels
- **Discord Bot**: Private server DM and server chat interface with daily morning digests and real-time pings.
- **Local CLI/Terminal Chat**: Local interactive environment for fast development, testing, and offline usage.

## Advisory Stance & Risk Profile
- **Moderate & Calibrated**: The agent provides balanced recommendations based on structured data evidence, with confidence levels directly proportional to its historical track record and data completeness.
