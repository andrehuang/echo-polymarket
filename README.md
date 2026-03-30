# Echo: Prediction Intelligence for Polymarket

A [Claude Code](https://claude.ai/claude-code) skill that analyzes [Polymarket](https://polymarket.com) prediction markets using multi-agent research, domain-specific rubrics, and structured probabilistic output.

Inspired by [UniPat AI's Echo system](https://unipat.ai/blog/Echo).

## How It Works

```
/echo <polymarket_url>
    |
    +-- Fetch market data (question, prices, resolution rules)
    |
    +-- Classify domain (politics / crypto / sports / economics)
    |
    +-- Load domain-specific rubric (12 evaluation dimensions)
    |
    +-- MAP: Spawn 3-5 research agents in parallel
    |   +-- Agent 1: Polling & public sentiment    [WebSearch]
    |   +-- Agent 2: Institutional & procedural    [WebSearch]
    |   +-- Agent 3: Historical base rates         [WebSearch]
    |   +-- Agent 4: Economic / contextual factors [WebSearch]
    |   +-- Agent 5: Timeline & resolution rules   [WebSearch]
    |
    +-- REDUCE: Synthesize sub-results
    |   +-- Resolve conflicts between agents
    |   +-- Weight by confidence & evidence quality
    |   +-- Assess counterfactual fragility
    |
    +-- Output structured prediction report
    |   +-- Probability + confidence classification
    |   +-- Evidence base with role tags (direct/supporting/contradicting)
    |   +-- Reversal scenarios & fragility score
    |   +-- Monitoring recommendations
    |
    +-- Log prediction for accuracy tracking
```

## Features

- **Map-Reduce Multi-Agent Research** -- Decomposes questions into orthogonal sub-tasks, runs parallel research agents, then synthesizes with conflict resolution
- **Domain-Specific Rubrics** -- 12-dimension evaluation criteria for politics, crypto, sports, and economics
- **Structured Output** -- Evidence classification, counterfactual fragility assessment, and monitoring recommendations
- **Prediction Tracking** -- Logs predictions, checks market resolutions, computes Brier scores, and tracks accuracy over time
- **Quick Mode** -- Single-agent fast analysis for rapid screening
- **No API Keys Required** -- Uses Claude Code's built-in WebSearch/WebFetch (covered by your subscription)

## Requirements

- [Claude Code](https://claude.ai/claude-code) (CLI, desktop app, or IDE extension)
- Python 3.8+
- `requests` package (`pip install requests`)

## Installation

### 1. Clone this repo

```bash
git clone https://github.com/andrehuang/echo-polymarket.git
cd echo-polymarket
```

### 2. Set ECHO_HOME

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export ECHO_HOME="/path/to/echo-polymarket"
```

### 3. Install the skill

Copy (or symlink) the skill into your Claude Code skills directory:

```bash
# Option A: Symlink (recommended -- stays in sync with repo)
ln -s "$ECHO_HOME/skill" ~/.claude/skills/echo

# Option B: Copy
cp -r "$ECHO_HOME/skill" ~/.claude/skills/echo
```

### 4. Install Python dependency

```bash
pip install requests
```

### 5. Verify

Open Claude Code and type `/echo` -- you should see the skill listed.

## Usage

### Interactive (Claude Code Skill)

#### Full Analysis (Map-Reduce)

```
/echo https://polymarket.com/event/next-us-president
```

Spawns 3-5 parallel research agents, each investigating a different angle. Takes 3-5 minutes. Produces a comprehensive report with evidence, fragility assessment, and monitoring recommendations.

### Quick Analysis

```
/echo --quick https://polymarket.com/event/bitcoin-ath-2026
```

Single-agent fast analysis. Takes ~1 minute. Good for initial screening.

### By Slug or Condition ID

```
/echo us-forces-enter-iran-by
/echo 0x6d0e09d0f04572d9b1adad84703458b0297bc5603b69dccbde93147ee4443246
```

### Check Resolved Predictions

```
/echo leaderboard
```

Or via command line:

```bash
cd $ECHO_HOME && python3 -m helpers.track_predictions leaderboard
cd $ECHO_HOME && python3 -m helpers.track_predictions check    # check for newly resolved markets
cd $ECHO_HOME && python3 -m helpers.track_predictions score    # raw accuracy JSON
```

## Output Example

```
Echo Prediction: US forces enter Iran by April 30?

| Metric             | Value                  |
|--------------------|------------------------|
| Echo probability   | 74%                    |
| Confidence         | medium                 |
| 90% CI             | [55%, 88%]             |
| Market price (YES) | 73.5%                  |
| Echo vs Market     | +0.5% higher           |
| Fragility          | 0.55 (moderate)        |

Evidence Base:
1. [DIRECT] Pentagon preparing "weeks of limited ground operations"...
2. [DIRECT] 50,000+ US troops in region; Marines and 82nd Airborne deploying...
3. [CONTRADICTING] Secretary Rubio: "We can achieve all objectives without ground troops"...

Reversal Scenarios:
- Surprise ceasefire by April 6: probability 15%, impact down 45%
- Trump extends deadline again: probability 25%, impact down 15%

Monitor:
- April 6 Strait of Hormuz deadline (check: daily)
- Pentagon/White House ground force authorization (check: daily)
```

### Daily Batch Runner (Automated Paper-Trading)

Echo includes a daily batch runner that can paper-trade alongside any Polymarket strategy. It scans markets, runs Echo analysis on each, logs predictions, and tracks accuracy over time -- all without placing real trades.

This lets you **test whether Echo's probability estimates beat the market** before committing real capital.

#### Quick Start

```bash
# Test with 3 markets first
python3 -m helpers.echo_daily_runner --scan-only
python3 -m helpers.echo_daily_runner --max-markets 3

# Full daily run (all markets, full Map-Reduce analysis)
python3 -m helpers.echo_daily_runner

# Quick mode (~1 min/market instead of ~5 min)
python3 -m helpers.echo_daily_runner --quick
```

Or use the shell script:

```bash
./run_echo_daily.sh                    # Full run
./run_echo_daily.sh --scan-only        # Just scan, see candidates
./run_echo_daily.sh --quick            # Fast single-agent mode
./run_echo_daily.sh --max-markets 5    # Limit scope
./run_echo_daily.sh --compare          # Compare vs your trading bot
```

#### How It Works

```
Daily Pipeline:

  1. SCAN       Fetch active Polymarket markets
                Apply filters (election, social media, etc.)
                Select candidates: YES price 10-60%, TTE 1-60d

  2. ANALYZE    For each market, run Echo via claude CLI
                Full Map-Reduce: 5 parallel research agents
                Or quick mode: single-agent analysis

  3. LOG        Save predictions to predictions.jsonl
                Record: echo_probability, market_price,
                confidence, domain, timestamp

  4. REPORT     Generate daily markdown report
                Flag disagreements (Echo vs Market > 10%)
                Paper trade signals (buy NO / buy YES)

  5. COMPARE    After markets resolve, score accuracy
                Brier scores: Echo vs Market baseline
                Track: does Echo beat the market?
```

#### Server Setup (for automated daily runs)

**Prerequisites:**
- A server or always-on machine with internet access
- Claude Code CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code && claude login`)
- Python 3.8+ with `requests` package
- This repo cloned with `$ECHO_HOME` set and skill installed (see [Installation](#installation))

**Step 1: Test manually**

```bash
# SSH to your server
ssh user@your-server

# First run — scan only to see what markets Echo would analyze
cd $ECHO_HOME
python3 -m helpers.echo_daily_runner --scan-only

# Test with a few markets
python3 -m helpers.echo_daily_runner --max-markets 3
```

**Step 2: Set up cron for daily automation**

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 10:00 UTC)
0 10 * * * cd /path/to/echo-polymarket && ./run_echo_daily.sh >> echo_cron.log 2>&1
```

**Step 3: Monitor accuracy over time**

```bash
# Check if any predicted markets have resolved
python3 -m helpers.track_predictions check

# See accuracy leaderboard
python3 -m helpers.track_predictions leaderboard

# Raw accuracy data as JSON
python3 -m helpers.track_predictions score
```

#### Running Alongside an Existing Trading Bot

If you already have a Polymarket trading bot, Echo can run as a paper-trading shadow:

```bash
# 1. Run your trading bot as usual (live or dry-run)
python your_trading_bot.py --bankroll 5000

# 2. Run Echo on the same markets (paper-trade only, no real orders)
python3 -m helpers.echo_daily_runner

# 3. Compare: did Echo agree or disagree with your bot's trades?
python3 -m helpers.echo_daily_runner --compare --date 2026-03-30
```

The comparison report shows for each market:
- What your bot did (traded or skipped, and why)
- What Echo predicted (probability + confidence)
- Whether they agreed or disagreed

Over time, this reveals whether Echo adds signal your bot doesn't capture.

#### Customizing the Market Scanner

The daily runner scans for markets matching these criteria:
- **YES price**: 10-60% (the "dark horse" range where mispricings are common)
- **Time to expiry**: 1-60 days
- **Filter mode**: `strict_elon_social` (elections + Elon Musk social media markets)

You can change the filter mode:

```bash
# Elections only (strictest filter)
python3 -m helpers.echo_daily_runner --filter-mode strict

# All politics + social media
python3 -m helpers.echo_daily_runner --filter-mode strict_elon_social
```

To add entirely new market categories (crypto, sports), edit the `scan_markets()` function in `helpers/echo_daily_runner.py`.

#### Output Structure

Each daily run produces:

```
echo_output/
  2026-03-30/
    batch.json          # All scanned candidate markets (JSON)
    report.md           # Daily analysis report (markdown)
    comparison.md       # Echo vs bot comparison
    0x1234abcd....json  # Individual market prediction
    0x5678efgh....json  # Individual market prediction
    run.log             # Full execution log
  2026-03-31/
    ...
```

#### Time Estimates

| Mode | Per Market | 35 Markets |
|------|-----------|------------|
| Full Map-Reduce (5 agents) | ~5 min | ~3 hours |
| Quick (single agent) | ~1 min | ~35 min |
| Scan only (no analysis) | — | ~10 sec |

## Domain Rubrics

Each domain has a 12-dimension rubric that guides the research agents:

| Domain | Key Dimensions |
|--------|---------------|
| **Politics** | Resolution criteria parsing, quantitative base rates, polling analysis, institutional constraints, timeline feasibility |
| **Crypto** | On-chain data, technical levels, macro/regulatory, protocol fundamentals, market microstructure |
| **Sports** | Statistical performance, injuries/roster, betting market intelligence, matchup analysis, environmental factors |
| **Economics** | Leading indicators, central bank communication, market pricing, policy context, geopolitical risk |

Rubrics are in `rubrics/` and can be customized.

## Project Structure

```
echo-polymarket/
+-- skill/
|   +-- SKILL.md                # Claude Code skill definition
+-- helpers/
|   +-- fetch_market.py         # Polymarket API client
|   +-- format_report.py        # Report formatting (markdown/JSON)
|   +-- track_predictions.py    # Prediction logging & Brier scoring
|   +-- echo_daily_runner.py    # Daily batch scanner & analyzer
+-- rubrics/
|   +-- politics.md             # 12-dimension politics rubric
|   +-- crypto.md               # 12-dimension crypto rubric
|   +-- sports.md               # 12-dimension sports rubric
|   +-- economics.md            # 12-dimension economics rubric
+-- run_echo_daily.sh           # Daily batch orchestration script
+-- README.md
+-- LICENSE
```

## How It Compares to Echo (UniPat AI)

This project reproduces key components of the [Echo prediction system](https://unipat.ai/blog/Echo):

| Echo Component | Our Implementation |
|---------------|-------------------|
| ReAct Agent (iterative think-search-observe) | Claude Code Agent subagents with WebSearch/WebFetch |
| Map-Reduce Architecture | Parallel Agent subagents (map) + synthesis (reduce) |
| Domain-Specific Rubrics | 12-dimension rubrics for 4 domains |
| Structured Output (evidence roles, fragility) | Evidence classification + reversal scenarios |
| Train-on-Future | N/A (we use real-time research, not model training) |
| Multi-Point Elo Evaluation | Brier score tracking + market comparison |

## License

MIT
