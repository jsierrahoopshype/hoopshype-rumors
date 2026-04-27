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

# ── URL cleaner ───────────────────────────────────────────────────────────────

def clean_url(url):
    """Strip UTM and other tracking parameters from URLs."""
    if not url:
        return url
    try:
        from urllib.parse import urlparse, urlencode, parse_qsl
        parsed = urlparse(url)
        STRIP = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content",
                 "utm_id","fbclid","gclid","mc_cid","mc_eid","r","ref","source",
                 "_hsenc","_hsmi","hsCtaTracking"}
        clean_qs = [(k,v) for k,v in parse_qsl(parsed.query) if k not in STRIP]
        clean = parsed._replace(query=urlencode(clean_qs))
        return clean.geturl()
    except:
        return url

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
        url    = clean_url(r.get("source_url") or "")
        tags   = r.get("tags") or r.get("players") or []
        if isinstance(tags, list):
            tags_str = ", ".join(tags)
        else:
            tags_str = str(tags)

        block = f"---\nDATE:{date} | SOURCE:{outlet}"
        if url:
            block += f" | URL:{url}"
        if tags_str:
            block += f" | TAGS:{tags_str}"
        block += f"\n{text}"
        if quote:
            block += f'\nQUOTE: "{quote}"'
        lines.append(block)

    return "\n\n".join(lines)


# ── Claude call ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior NBA beat writer for HoopsHype writing the daily rumors roundup.

FORMAT — follow this precisely:

1. HEADLINE: Write a single headline in this format:
   "NBA Rumors Wrap: [story A], [story B] and [story C]"
   Rules:
   - 15-18 words total including "NBA Rumors Wrap:"
   - Sentence case after the colon (not all caps)
   - Full player names, not last names only
   - Pick the 2-3 most newsworthy storylines, separated by commas — no "and" before the last item
   - No quotes around the headline

2. Lead paragraph: Start immediately after the headline with the single most newsworthy story.
   4-6 sentences. Give it room. Bold all player and team names on first mention.
   Set context — why does this matter, what is the situation around it, what happens next.
   Name the reporter/outlet who broke the story once, naturally (e.g. "per Shams Charania").
   This is not a bullet. Write it like the opening of a real news story.

3. Transition line: "Here are more notes from around the league:" (adjust to "the East" or "the West" if conference-specific).

4. 8-14 bullet points (•) for secondary items. Rules:
   — GROUP related items together. All bullets about the same game, team or story must appear consecutively.
     Example: all Wolves-related bullets together, all Rockets-Lakers bullets together, etc.
     Never split a storyline across non-adjacent bullets.
   — When combining two related items into one bullet, use a natural transition between them.
     Do NOT just stack two facts back to back with no connective tissue.
     Use bridging phrases like: "On a related note,", "Meanwhile,", "Adding to that,",
     "That comes alongside...", "His agent also said...", "Context:" or similar.
     The bullet should read as one cohesive thought, not two separate sentences stapled together.
     EXAMPLE (good):
     "Rich Paul says the Lakers should do 'everything they can' to keep LeBron James in the organization.
     'The Lakers should be delighted that he played for them,' Paul said. On a related note, ESPN's
     Brian Windhorst said LeBron looked so poor returning from his sciatica issue that Windhorst told
     his bosses to begin planning retirement content."
     EXAMPLE (bad):
     "Rich Paul says the Lakers should keep LeBron. ESPN's Brian Windhorst said LeBron looked poor
     returning from his sciatica issue and told his bosses to plan retirement content."
   — Do NOT use "(Team Name)" after a player name. Weave the team into the sentence naturally.
     WRONG: "Kevin Durant (Houston Rockets) has been upgraded..."
     RIGHT: "Kevin Durant has been upgraded for Houston..."
   — 2-3 sentences max per bullet
   — SOURCING: Always link to the source URL when one exists in the data.
     If there is a reporter name in the data, credit them in the lead only — not in bullets.
     In bullets, just hyperlink a word to the URL: "...per <a href="URL">HoopsHype</a>" or "...per <a href="URL">ESPN</a>"
     If there is a URL but no outlet name, use the domain as the link text.
     If there is NO URL in the data, omit attribution entirely — do not invent a link.

STALENESS RULE — CRITICAL:
   The archive runs every morning. Some entries will be from the previous day and may be outdated.
   SKIP any item that reports a player's pre-game injury status (questionable, doubtful, out)
   for a game that has ALREADY been played by the time this roundup runs.
   HOW TO TELL: If the archive also contains a game result or postgame quotes for that same game,
   the game has already been played — pre-game injury reports for it are stale and must be omitted.
   EXCEPTION: Include the injury only if it is still relevant going forward
   (e.g. a player missed Game 3 and their status for Game 4 is still unknown).

SOURCING RULES — CRITICAL. READ CAREFULLY:
Each archive entry arrives in this format:
  DATE:YYYY-MM-DD | SOURCE:Outlet Name | URL:https://...
  TEXT: the rumor text
  QUOTE: "verbatim quote if present"

- Every factual claim you write MUST be hyperlinked to the URL from that entry.
  In HTML: <a href="URL">linked text</a> where the linked text is a natural word in the sentence.
  In Slack: use Slack hyperlink format <URL|linked text> — NEVER paste raw URLs inline.
  The linked text should be a word already in the sentence — a player name, team name,
  or action word. Never use "click here" or the raw URL as the link text.
- In bullets: NEVER use "per [outlet]" or "per [reporter]" phrases. No exceptions.
  Just hyperlink a meaningful word or phrase in the sentence to the source URL.
  The hyperlink IS the attribution. The reader can see where it goes.
  RIGHT: Kevin Durant <a href="URL">missed Game 4</a> with a bone bruise in his ankle.
  WRONG: Kevin Durant missed Game 4 with a bone bruise, per ESPN.
  WRONG: per Shams Charania, Kevin Durant missed Game 4.
- The hyperlinked word should be a fact, action or detail — never the reporter's name,
  never the outlet name, never "here" or "this report."
  RIGHT: ...the Rockets <a href="URL">avoided a sweep</a> Sunday night.
  WRONG: ...the Rockets avoided a sweep Sunday night, per <a href="URL">ESPN</a>.
- "Per [name]" is allowed ONLY in the lead paragraph, and ONLY for genuine newsbreakers:
  Shams Charania, Adrian Wojnarowski, Marc Stein, Chris Haynes, HoopsHype exclusives.
  Everyone else gets a hyperlinked fact, no name drop.
- If an entry has NO URL field, write the fact with no link and no attribution phrase.
- NEVER invent, guess or complete a person's name. Each entry includes a TAGS field
  listing the people mentioned in that rumor. Only use names that appear in TAGS,
  TEXT or QUOTE — never infer or complete a partial name from context.
  If a quote has no speaker identified in those fields, do not attribute it to anyone.

BULLET STRUCTURE RULES:
- Use judgment on length. If a game has one clean storyline, one tight bullet. If it has
  two genuinely connected angles (e.g. an ejection that led to a fine), combine them with
  a natural transition. If two players from the same game have unrelated stories, split them.
- Each bullet should have one clear throughline. Do not pack in unrelated facts just because
  they come from the same game. A bullet that wanders loses the reader.
- Aim for somewhere between HoopsRumors tight and The Athletic notes column — factual and
  efficient, but with enough texture that each item feels like it was written by a person,
  not assembled from a database. A good quote earns its own sentence. Context earns one too.
- When an anecdote has natural color — a funny exchange, an unexpected detail, a human moment —
  write it like a story, not a transcript summary. Set the scene briefly, let the moment land.
  Example: instead of "Sengun asked if he mispronounced any words and Thompson said he did once
  but was still motivated," write it so the reader can picture the locker room.
- Do not use full team names when a shorter version works. "Nuggets-Timberwolves scuffle"
  not "Denver Nuggets-Minnesota Timberwolves scuffle." "the Rockets" not "the Houston Rockets."
- Write as many bullets as the news warrants. Do not pad, do not cut good stories to hit a number.

STYLE RULES:
- HoopsHype-sourced items are priority — flag them prominently.
- Do NOT fabricate quotes, details, or links not present in the data.
- Do NOT add section headers or subheadings beyond the headline.
- Target 700-1000 words total.
- Natural, human, direct. Not stiff wire-copy, not chatty. Think a good NBA beat writer
  filing a notes column — Frank Urbina, not a press release.
- BANNED PUNCTUATION: No em-dashes (— or --) anywhere in the output. Use a comma or
  a new sentence instead. This applies to ALL output including examples you generate mentally.
- BANNED WORDS AND PHRASES — never use any of these:
  "notably," "it's worth noting," "underscoring," "highlighting," "showcasing," "delve,"
  "crucial," "game-changing," "landscape," "nuanced," "multifaceted," "pivotal," "realm,"
  "robust," "seamless," "leverage" (as a verb), "utilize," "amidst," "furthermore,"
  "nevertheless," "in the wake of," "moving forward," "going forward," "at the end of the day,"
  "it remains to be seen," "only time will tell," "adding to the intrigue."
- Do not over-explain why something matters. Let the facts speak.
- Do not editorialize. Report, don't comment.
- Read your output before finalizing. If any sentence sounds like it was written by a machine,
  rewrite it.

OUTPUT TWO VERSIONS separated by exactly this line: ===SLACK===

Version 1 (HTML for Presto CMS):
- First line: the headline wrapped in <h2> tags
- Then: <p>, <strong>, <a href="...">, <ul>, <li> tags only. No CSS, no divs.

Version 2 (Plain text for Slack):
- First line: *headline* in Slack bold
- Then: plain text, *bold* for player/team names, bullet points with •, no HTML tags.
- Write the FULL article — do not truncate or summarize. Every bullet point must appear."""


def call_claude(user_msg):
    if not AI_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 5000,
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
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode())
            return resp["content"][0]["text"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Anthropic API error {e.code}: {error_body}")


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


def send_slack_block(text):
    """Send a single Slack message block (max 3000 chars)."""
    payload = json.dumps({
        "blocks": [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        }]
    }).encode()
    req = urllib.request.Request(SLACK, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30):
        pass


def post_slack(slack_text, date_label, count, hours):
    if not SLACK:
        print("  ℹ  No SLACK_WEBHOOK_URL — skipping Slack post")
        return

    header = f"*🏀 HoopsHype Wrapped — {date_label}* (last {hours}h · {count} rumors)\n\n"
    full   = header + slack_text

    # Split into chunks of max 2950 chars, breaking on newlines where possible
    CHUNK = 2950
    chunks = []
    remaining = full
    while remaining:
        if len(remaining) <= CHUNK:
            chunks.append(remaining)
            break
        # Find last newline before the limit
        split_at = remaining.rfind("\n", 0, CHUNK)
        if split_at == -1:
            split_at = CHUNK
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    MAX_SLACK_MSGS = 6
    if len(chunks) > MAX_SLACK_MSGS:
        # Merge last chunks to stay within limit
        chunks = chunks[:MAX_SLACK_MSGS-1] + ["\n".join(chunks[MAX_SLACK_MSGS-1:])]
    try:
        for i, chunk in enumerate(chunks, 1):
            if len(chunks) > 1:
                chunk = f"_({i}/{len(chunks)})_\n" + chunk
            send_slack_block(chunk)
        print(f"  ✓ Posted to Slack ({len(chunks)} message(s))")
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
