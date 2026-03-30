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

### Daily Batch Runner (Server Automation)

Run Echo as a daily paper-trading pipeline alongside your existing trading bot.

```bash
# Full daily run: scan markets → analyze with Echo → generate report
./run_echo_daily.sh

# Scan-only (see what markets Echo would analyze)
./run_echo_daily.sh --scan-only

# Quick mode (single-agent, ~1min/market instead of ~5min)
./run_echo_daily.sh --quick

# Limit to N markets (for testing)
./run_echo_daily.sh --max-markets 5

# Compare Echo predictions vs bot's actual trades
./run_echo_daily.sh --compare
```

**Setup for daily automation (cron):**

```bash
# Add to crontab on your server (run daily at 10:00 UTC)
0 10 * * * cd /path/to/echo-polymarket && ./run_echo_daily.sh >> echo_cron.log 2>&1
```

**What the daily runner does:**
1. Scans Polymarket using the same filters as your trading bot (`strict_elon_social`)
2. For each candidate market (YES price 10-60%, TTE 1-60 days), runs full Echo analysis via `claude` CLI
3. Logs all predictions to `predictions.jsonl` with timestamps
4. Generates a daily report with:
   - Echo probability vs market price for every market
   - Major disagreements (>10% delta) flagged
   - Paper trade signals (where Echo thinks the market is mispriced)
5. Compares against your bot's actual trade/rejection decisions

**Output structure:**
```
echo_output/
  2026-03-30/
    batch.json       # Scanned markets
    report.md        # Daily analysis report
    comparison.md    # Echo vs bot comparison
    0x1234...json    # Individual market predictions
    run.log          # Execution log
```

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
|   +-- SKILL.md              # Claude Code skill definition
+-- helpers/
|   +-- fetch_market.py       # Polymarket API client
|   +-- format_report.py      # Report formatting (markdown/JSON)
|   +-- track_predictions.py  # Prediction logging & Brier scoring
+-- rubrics/
|   +-- politics.md           # 12-dimension politics rubric
|   +-- crypto.md             # 12-dimension crypto rubric
|   +-- sports.md             # 12-dimension sports rubric
|   +-- economics.md          # 12-dimension economics rubric
+-- run_echo_daily.sh          # Daily batch orchestration script
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
