# NLP Sentiment Analysis Module

Narrative drift detection and sentiment analysis for SEC filings, earnings transcripts, and Discord chat data.

## Discord Integration

Use DiscordChatExporter to export Discord channel data as JSON, then import into the NLP pipeline.

### Discord Export Import

#### Step 1: Download DiscordChatExporter

Download from: https://github.com/Tyrrrz/DiscordChatExporter/releases

- **Linux**: `DiscordChatExporter.Cli.linux-x64.zip` or `linux-arm64.zip`
- **macOS**: `DiscordChatExporter.Cli.osx-x64.zip` or `osx-arm64.zip`
- **Windows**: `DiscordChatExporter.Cli.win-x64.zip`

Extract the zip (the directory name matches the zip filename):
```bash
cd ~/Downloads
unzip DiscordChatExporter.Cli.linux-arm64.zip
```

#### Step 2: Get Your Discord User Token

1. Open Discord **in your web browser** (not the desktop app): https://discord.com/app
2. Open Developer Tools:
   - **Chrome/Firefox/Edge**: Press `F12`
   - **Safari**: First enable Developer menu (Safari → Settings → Advanced → "Show Develop menu"), then Develop → Show Web Inspector
3. Click the **Network** tab
4. Refresh the page (`F5` or `Cmd+R`)
5. In the filter box, type `api`
6. Click any request to `discord.com/api/...`
7. Look in **Headers** → **Request Headers** → `Authorization`
8. Copy the token value (long string of characters)

**Security Note**: Your token gives full access to your Discord account. Never share it. The token is only sent to Discord's servers during export - see [security review](#security).

#### Step 3: Get Server and Channel IDs

First, enable Developer Mode in Discord:
- User Settings → Advanced → Enable "Developer Mode"

**Get Server ID:**
- Right-click the server icon → "Copy Server ID"

**Get Channel ID:**
- Right-click the channel name (e.g., #stocks-chat) → "Copy Channel ID"

#### Step 4: List Available Channels

Verify your token works and see available channels:

```bash
# List all servers you're in
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli guilds \
  -t "YOUR_TOKEN"

# List all channels in a specific server
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli channels \
  -t "YOUR_TOKEN" \
  -g SERVER_ID
```

#### Step 5: Export Channel Data

**Export a single channel:**
```bash
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli export \
  -t "YOUR_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  -o "$(pwd)/alternative/nlp_sentiment/data/discord_exports/"
```

**Export multiple channels:**
```bash
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli export \
  -t "YOUR_TOKEN" \
  -c CHANNEL_ID_1 CHANNEL_ID_2 CHANNEL_ID_3 \
  -f Json \
  -o "$(pwd)/alternative/nlp_sentiment/data/discord_exports/"
```

**Export entire server:**
```bash
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli exportguild \
  -t "YOUR_TOKEN" \
  -g SERVER_ID \
  -f Json \
  -o "$(pwd)/alternative/nlp_sentiment/data/discord_exports/"
```

**Limit to recent messages (recommended for large channels):**

Large channels can take a very long time to export. Use `--after` to limit:

```bash
# Last 2 weeks only
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli export \
  -t "YOUR_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  --after "2026-01-01" \
  -o "$(pwd)/alternative/nlp_sentiment/data/discord_exports/"
```

Date format is `YYYY-MM-DD`. Adjust the date as needed.

**Export with date range (both start and end):**
```bash
~/Downloads/DiscordChatExporter.Cli.linux-arm64/DiscordChatExporter.Cli export \
  -t "YOUR_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  --after "2025-01-01" \
  --before "2025-01-31" \
  -o "$(pwd)/alternative/nlp_sentiment/data/discord_exports/"
```

#### Step 6: Import into Atemoya

**Option A: Using quickstart.sh**
```bash
./quickstart.sh
# Navigate: Monitoring → NLP Sentiment → Import Discord Export
```

**Option B: Direct command**
```bash
cd alternative/nlp_sentiment/python/fetch
../../../../../../.venv/bin/python3 import_discord_export.py \
  --dir ~/claude/atemoya/alternative/nlp_sentiment/data/discord_exports/
```

**With filters:**
```bash
# Filter by tickers
uv run import_discord_export.py --dir ./exports --tickers AAPL NVDA TSLA

# Only last 7 days
uv run import_discord_export.py --dir ./exports --days 7
```

#### Output

After import, data is saved to `data/discord/`:
- `discord_messages.json` - All parsed messages
- `discord_aggregates.json` - Per-ticker sentiment aggregates
- `documents/` - Pipeline-compatible documents per ticker
- `import_metadata.json` - Import session metadata

---

## Security

### DiscordChatExporter Code Review

DiscordChatExporter is open source (MIT licensed) with 10k+ GitHub stars.

| Aspect | Finding |
|--------|---------|
| Token storage | Private field in memory only, never logged or saved |
| Token destination | Only sent to `https://discord.com/api/v10/` |
| External domains | None - only contacts Discord's official API |
| Source code | https://github.com/Tyrrrz/DiscordChatExporter |

### Data Privacy

The following are gitignored and never committed:
- `data/discord/` - Imported message data
- `data/discord_exports/` - Raw export files

---

## Sentiment Analysis

### Ticker Extraction
Detects ticker mentions in two formats:
- `$AAPL` - Cashtag format
- `AAPL` - All-caps 2-5 letter words (with blacklist filtering)

### Sentiment Signals

**Emoji Sentiment:**
| Bullish | Bearish |
|---------|---------|
| 🚀 📈 💎 🙌 💪 🔥 💰 🤑 🟢 | 📉 💀 🩸 😱 🔴 🐻 ☠️ |

**Keyword Sentiment:**
| Bullish | Bearish |
|---------|---------|
| buy, long, calls, moon, bullish, squeeze, breakout, oversold | sell, short, puts, dump, bearish, crash, tank, overbought |

### Output Signals
- **BULLISH**: Combined sentiment > 0.1
- **BEARISH**: Combined sentiment < -0.1
- **NEUTRAL**: Combined sentiment between -0.1 and 0.1

---

## Full Pipeline

Run the complete NLP pipeline including SEC filings and earnings transcripts:

```bash
./quickstart.sh
# Navigate: Monitoring → NLP Sentiment → Run Full Pipeline
```

Or directly:
```bash
.venv/bin/python3 alternative/nlp_sentiment/python/pipeline.py \
  AAPL NVDA TSLA \
  --quarters 12 \
  --output alternative/nlp_sentiment/output
```
