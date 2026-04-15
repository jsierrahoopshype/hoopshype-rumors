#!/usr/bin/env python3
"""
HoopsHype Wrapped — Daily NBA Rumors Roundup Generator
Fetches last N hours from the HoopsHype Archive, writes a
HoopsRumors-style notes post via Claude, outputs HTML + Slack.

Usage:
  python hoopshype_wrapped.py                  # last 24h
  python hoopshype_wrapped.py --hours 12       # last 12h
  python hoopshype_wrapped.py --hours 48       # last 48h
  python hoopshype_wrapped.py --no-slack       # skip Slack

Environment variables (set locally or as GitHub Secrets):
  HH_API_KEY          HoopsHype Rumors Worker API key
  ANTHROPIC_API_KEY   Claude API key
  SLACK_WEBHOOK_URL   Slack incoming webhook URL (optional)
"""

import argparse, json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone

# ── Config ────────────────────────────────────────────────────────────────────
WORKER  = "https://hoopshype-rumors-api.thejorgesierra.workers.dev"
HH_KEY  = os.environ.get("HH_API_KEY", "")
AI_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
SLACK   = os.environ.get("SLACK_WEBHOOK_URL", "")

ARCHIVE_HEADERS = {
    "Origin":  "https://jsierrahoopshype.github.io",
    "Referer": "https://jsierrahoopshype.github.io/hoopshype-rumors/hoopshype_rumors_tool.html",
    "User-Agent": "HoopsHype-Wrapped/1.0",
    "X-API-Key": HH_KEY,
}

# Reporters and outlets that signal high-quality sourcing
PREMIUM_SOURCES = [
    "wojnarowski", "woj", "shams", "charania", "haynes", "stein",
    "windhorst", "youngmisuk", "macmahon", "shelburne", "mannix",
    "hoopshype", "the athletic", "espn", "bleacher report",
]

# Keywords that signal a newsworthy rumor
NEWSWORTHY_KW = [
    "trade", "sign", "waive", "extend", "extension", "buyout", "release",
    "fire", "fired", "hire", "hired", "interested", "pursuing", "targeting",
    "contract", "deal", "offer", "free agent", "draft", "suspend",
    "interview", "mutual interest", "exploring", "seeking",
]


# ── Archive fetching ──────────────────────────────────────────────────────────

def fetch_endpoint(endpoint):
    req = urllib.request.Request(f"{WORKER}{endpoint}", headers=ARCHIVE_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
            return data if isinstance(data, list) else data.get("rumors", [])
    except Exception as e:
        print(f"  ⚠  Fetch failed ({endpoint}): {e}", file=sys.stderr)
        return []


def load_rumors(hours):
    print(f"Fetching archive (last {hours}h)…")

    # Latest is always fetched; pull part 1 too if scope > 12h to ensure coverage
    all_r = fetch_endpoint("/api/rumors/latest")
    if hours > 12:
        part1 = fetch_endpoint("/api/rumors/part/1")
        seen = {r.get("source_url", "") for r in all_r}
        all_r.extend(r for r in part1 if r.get("source_url", "") not in seen)

    print(f"  Loaded {len(all_r):,} raw entries")

    # Filter by date — archive_date is YYYY-MM-DD
    cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d")
    recent = [r for r in all_r if (r.get("archive_date") or r.get("date") or "") >= cutoff_str]

    print(f"  → {len(recent)} entries within last {hours}h")
    return recent


# ── Scoring & ranking ─────────────────────────────────────────────────────────

def score_rumor(r):
    text   = ((r.get("text") or "") + " " + (r.get("quote") or "")).lower()
    outlet = (r.get("outlet") or "").lower()
    s = 0
    # Premium source bonus
    if any(p in outlet or p in text for p in PREMIUM_SOURCES):
        s += 10
    # HoopsHype exclusive gets extra bump
    if "hoopshype" in outlet.lower():
        s += 5
    # Direct quote = more substantive
    if r.get("quote") and len(r.get("quote", "")) > 50:
        s += 6
    # Newsworthy keywords
    s += sum(2 for kw in NEWSWORTHY_KW if kw in text)
    # Longer text = more depth
    if len(r.get("text", "")) > 300:
        s += 3
    return s


def build_payload(rumors, max_items=60):
    """Sort by score, take top N, format for Claude."""
    scored = sorted(rumors, key=score_rumor, reverse=True)
    top    = scored[:max_items]

    lines = []
    for r in top:
        date   = r.get("archive_date", "")
        outlet = r.get("outlet", "Unknown")
        text   = (r.get("text") or "")[:450]
        quote  = (r.get("quote") or "")
        url    = (r.get("source_url") or "")

        block = f"---\nDATE:{date} | SOURCE:{outlet}"
        if url:
            block += f" | URL:{url}"
        block += f"\n{text}"
        if quote:
            block += f'\nQUOTE: "{quote}"'
        lines.append(block)

    return "\n\n".join(lines)


# ── Claude call ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior NBA beat writer for HoopsHype writing the daily rumors roundup.

FORMAT — follow this precisely:

1. Lead paragraph (no headline): Start immediately with the single most newsworthy story. 3-5 sentences. Bold all player and team names on first mention.

2. Transition line: "Here are more notes from around the league:" (adjust to "the East" or "the West" if all items are conference-specific).

3. 8-14 bullet points (•) for secondary items. Each bullet:
   — Bold the player name
   — Include team in parens on first mention
   — 2-3 sentences max
   — Attribute naturally in the text ("per Woj", "writes Shams", "per HoopsHype's [reporter]")
   — Include the source URL as a hyperlink on the reporter/outlet name

STYLE RULES:
- If HoopsHype is the source, always credit it as "per HoopsHype" — these are priority items.
- Do NOT fabricate quotes, details, or links not present in the data.
- Do NOT add section headers or subheadings.
- Target 600-900 words total.
- Write like you're filing for deadline — crisp, authoritative, no fluff.

OUTPUT TWO VERSIONS separated by exactly this line: ===SLACK===

Version 1 (HTML for Presto CMS):
Use <p>, <strong>, <a href="...">, <ul>, <li> tags only. No CSS, no divs.

Version 2 (Plain text for Slack):
Use *bold* for Slack markdown. Bullet points with •. No HTML tags."""


def call_claude(user_msg):
    if not AI_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":     "application/json",
            "x-api-key":        AI_KEY,
            "anthropic-version": "2023-06-01",
        }
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())
        return resp["content"][0]["text"]


def generate_roundup(rumors, hours, date_label):
    payload  = build_payload(rumors)
    user_msg = (
        f"DATE: {date_label}\n"
        f"SCOPE: Last {hours} hours\n"
        f"TOTAL ENTRIES: {len(rumors)}\n\n"
        f"Write the HoopsHype Wrapped roundup from this archive data:\n\n"
        f"{payload}"
    )
    print(f"  Sending {len(rumors)} entries to Claude…")
    return call_claude(user_msg)


def split_outputs(raw):
    """Split Claude response into HTML and Slack versions."""
    if "===SLACK===" in raw:
        html, slack = raw.split("===SLACK===", 1)
        return html.strip(), slack.strip()
    return raw.strip(), raw.strip()


# ── Output helpers ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>HoopsHype Wrapped — {date}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 780px; margin: 40px auto;
          padding: 0 24px; line-height: 1.75; color: #111; }}
  a    {{ color: #c8102e; }}
  ul   {{ margin: .5rem 0 1rem; }}
  li   {{ margin-bottom: .6rem; }}
  .meta {{ font-size: 11px; color: #888; text-transform: uppercase;
           letter-spacing: .08em; margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<p class="meta">HoopsHype Wrapped &middot; {date}</p>
{body}
</body>
</html>"""


def save_html(html_body, filename, date_label):
    full = HTML_TEMPLATE.format(date=date_label, body=html_body)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(full)
    print(f"  ✓ HTML saved → {filename}")


def post_slack(slack_text, date_label, count, hours):
    if not SLACK:
        print("  ℹ  No SLACK_WEBHOOK_URL — skipping Slack post")
        return

    header = f"*🏀 HoopsHype Wrapped — {date_label}* (last {hours}h · {count} rumors)\n\n"
    full   = header + slack_text

    # Slack text block limit is 3000 chars
    body = full[:2950] + "…" if len(full) > 2950 else full

    payload = json.dumps({
        "blocks": [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": body}
        }]
    }).encode()

    req = urllib.request.Request(SLACK, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            print("  ✓ Posted to Slack")
    except Exception as e:
        print(f"  ⚠  Slack post failed: {e}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HoopsHype Wrapped — Daily Rumors Roundup")
    parser.add_argument("--hours",    type=int,  default=24,  help="Hours to look back (default: 24)")
    parser.add_argument("--output",   type=str,  default="",  help="HTML output filename (auto-named if empty)")
    parser.add_argument("--no-slack", dest="no_slack", action="store_true", help="Skip Slack posting")
    args = parser.parse_args()

    date_label = datetime.now().strftime("%B %d, %Y")
    filename   = args.output or f"hoopshype_wrapped_{datetime.now().strftime('%Y-%m-%d')}.html"

    print(f"\n{'='*60}")
    print(f"HoopsHype Wrapped — {date_label} (last {args.hours}h)")
    print(f"{'='*60}\n")

    # 1. Load
    rumors = load_rumors(args.hours)
    if not rumors:
        print("❌  No rumors found for this time period.")
        sys.exit(1)

    # 2. Generate
    print("\nGenerating roundup with Claude…")
    raw          = generate_roundup(rumors, args.hours, date_label)
    html_body, slack_text = split_outputs(raw)

    # 3. Save HTML (Presto-ready)
    save_html(html_body, filename, date_label)

    # 4. Slack
    if not args.no_slack:
        post_slack(slack_text, date_label, len(rumors), args.hours)

    # 5. Print plain text to console (useful in GitHub Actions logs)
    print(f"\n{'─'*60}")
    print("PLAIN TEXT PREVIEW:")
    print("─"*60)
    print(slack_text[:1500])
    if len(slack_text) > 1500:
        print(f"… [{len(slack_text)-1500} more chars]")

    print(f"\n✅  Done. HTML saved: {filename}")


if __name__ == "__main__":
    main()
