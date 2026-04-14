#!/usr/bin/env python3
"""
Analyze git history of the 2026 Maryland legislative pipeline
and generate an interactive HTML report.
"""

import subprocess
import re
import json
import os
from collections import Counter
from datetime import datetime, timedelta

REPO_PATH = os.path.dirname(os.path.abspath(__file__))


def run_git(args):
    result = subprocess.run(
        ['git'] + args, capture_output=True, text=True, cwd=REPO_PATH
    )
    return result.stdout


def shift_date(date_str):
    """Shift a YYYY-MM-DD string back one day.
    The pipeline runs at midnight Eastern, so each run captures the
    previous day's legislative changes."""
    return (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')


def get_pipeline_commits():
    lines = run_git(['log', '--format=%H|%ci|%s']).strip().split('\n')
    commits = []
    for line in lines:
        if not line:
            continue
        parts = line.split('|', 2)
        if len(parts) < 3:
            continue
        hash_, datetime_str, msg = parts
        msg = msg.strip()

        auto_match = re.match(r'Automated pipeline update (2026-\d{2}-\d{2})', msg)
        if auto_match:
            commits.append({
                'hash': hash_.strip(),
                'date': shift_date(auto_match.group(1)),
                'label': msg,
                'is_manual': False,
            })
        elif msg == 'Rerun 2026':
            commits.append({
                'hash': hash_.strip(),
                'date': shift_date('2026-04-09'),
                'label': 'Manual rerun (fills 4/6–4/8 gap)',
                'is_manual': True,
            })

    commits.sort(key=lambda x: x['date'])
    return commits


def analyze_commit(hash_):
    output = run_git(['show', hash_, '--name-status', '--format='])

    new_bills = []
    modified_bills = []
    amendment_docs = []
    amendment_docs_by_bill = Counter()
    amended_bills_set = set()
    new_fiscal_notes = []
    updated_fiscal_notes = []

    for line in output.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        status = parts[0].strip()
        filepath = parts[1].strip()

        if not filepath.startswith('data/2026rs/md/'):
            continue

        filename = os.path.basename(filepath)

        fn_match = re.match(r'^([HS]B\d+)_fn\.md$', filename)
        if fn_match:
            bill_num = fn_match.group(1)
            if status == 'A':
                new_fiscal_notes.append(bill_num)
            elif status == 'M':
                updated_fiscal_notes.append(bill_num)
            continue

        if filename.endswith('_amended.md'):
            continue

        amd_match = re.match(r'^([HS]B\d+)_amd\d+_\d+\.md$', filename)
        if amd_match:
            if status == 'A':
                bill_num = amd_match.group(1)
                amendment_docs.append(filename)
                amended_bills_set.add(bill_num)
                amendment_docs_by_bill[bill_num] += 1
            continue

        bill_match = re.match(r'^([HS]B\d+)\.md$', filename)
        if bill_match:
            bill_num = bill_match.group(1)
            if status == 'A':
                new_bills.append(bill_num)
            elif status == 'M':
                modified_bills.append(bill_num)

    return {
        'new_bills': sorted(new_bills),
        'modified_bills': sorted(modified_bills),
        'new_bills_count': len(new_bills),
        'modified_bills_count': len(modified_bills),
        'amendment_docs_count': len(amendment_docs),
        'amendment_docs_by_bill': dict(amendment_docs_by_bill),
        'amended_bills': sorted(list(amended_bills_set)),
        'amended_bills_count': len(amended_bills_set),
        'new_fiscal_notes': sorted(new_fiscal_notes),
        'updated_fiscal_notes': sorted(updated_fiscal_notes),
        'new_fiscal_notes_count': len(new_fiscal_notes),
        'updated_fiscal_notes_count': len(updated_fiscal_notes),
    }


def build_html(daily_data):
    # Total session bills from authoritative legislation.json
    leg_path = os.path.join(REPO_PATH, 'data/2026rs/legislation.json')
    try:
        with open(leg_path, 'r', encoding='utf-8') as f:
            total_session_bills = len(json.load(f))
    except Exception:
        total_session_bills = 1890  # fallback

    # Subject counts from frontend_data.json
    broad_counts = Counter()
    narrow_counts = Counter()
    fe_path = os.path.join(REPO_PATH, 'data/2026rs/frontend_data.json')
    try:
        with open(fe_path, 'r', encoding='utf-8') as f:
            fe_data = json.load(f)
        for bill in fe_data:
            for s in (bill.get('BroadSubjects') or []):
                broad_counts[s['Name']] += 1
            for s in (bill.get('NarrowSubjects') or []):
                narrow_counts[s['Name']] += 1
    except Exception:
        pass
    top3_broad = broad_counts.most_common(3)
    top3_narrow = narrow_counts.most_common(3)

    # Bills that existed before the first pipeline run (Jan 14 – Feb 3)
    first_commit = daily_data[0]['hash']
    parent_out = run_git(['rev-parse', first_commit + '^']).strip()
    pre_pipeline_bills = 0
    if parent_out:
        tree = run_git(['ls-tree', '-r', '--name-only', parent_out])
        pre_pipeline_bills = sum(
            1 for f in tree.splitlines()
            if re.match(r'data/2026rs/md/[HS]B\d+\.md$', f)
        )

    total_new_bills = sum(d['new_bills_count'] for d in daily_data)
    total_modified = sum(d['modified_bills_count'] for d in daily_data)
    total_amend_docs = sum(d['amendment_docs_count'] for d in daily_data)
    total_fn_new = sum(d['new_fiscal_notes_count'] for d in daily_data)
    total_fn_updated = sum(d['updated_fiscal_notes_count'] for d in daily_data)
    num_runs = len(daily_data)

    def day_activity(d):
        return (d['new_bills_count'] + d['modified_bills_count'] +
                d['amendment_docs_count'] + d['new_fiscal_notes_count'] +
                d['updated_fiscal_notes_count'])

    busiest = max(daily_data, key=day_activity)
    most_new_bills = max(daily_data, key=lambda d: d['new_bills_count'])
    most_amendments = max(daily_data, key=lambda d: d['amendment_docs_count'])

    session_start = datetime.strptime('2026-01-14', '%Y-%m-%d')  # actual session opening
    session_end = datetime.strptime('2026-04-13', '%Y-%m-%d')  # actual Sine Die
    session_days = (session_end - session_start).days + 1

    date_labels = [
        datetime.strptime(d['date'], '%Y-%m-%d').strftime('%b %-d')
        for d in daily_data
    ]

    # Cumulative: bills start from pre-pipeline baseline; FN = new-only
    cum_bills, cum_amend, cum_fn = [], [], []
    rb = pre_pipeline_bills
    ra = rf = 0
    for d in daily_data:
        rb += d['new_bills_count']
        ra += d['amendment_docs_count']
        rf += d['new_fiscal_notes_count']   # new-only, not updates
        cum_bills.append(rb)
        cum_amend.append(ra)
        cum_fn.append(rf)

    # Last-2-weeks sprint stats — use amendments, not new bills
    last_14_start = len(daily_data) - sum(
        1 for d in daily_data
        if (session_end - datetime.strptime(d['date'], '%Y-%m-%d')).days < 14
    )
    sprint_amend = sum(d['amendment_docs_count'] for d in daily_data[last_14_start:])
    sprint_fn = sum(d['new_fiscal_notes_count'] + d['updated_fiscal_notes_count']
                    for d in daily_data[last_14_start:])
    sprint_pct_amend = round(sprint_amend / max(total_amend_docs, 1) * 100)
    sprint_pct_fn = round(sprint_fn / max(total_fn_new + total_fn_updated, 1) * 100)

    # ── Bill-level superlatives ──────────────────────────────
    bill_mod_counts = Counter()
    bill_amend_counts = Counter()
    bill_fn_update_counts = Counter()
    bill_introduced_on = {}   # bill → date first seen as 'A'
    bill_last_touched_on = {} # bill → latest date any change

    for d in daily_data:
        dt = d['date']
        for b in d['new_bills']:
            if b not in bill_introduced_on:
                bill_introduced_on[b] = dt
            bill_last_touched_on[b] = dt
        for b in d['modified_bills']:
            bill_mod_counts[b] += 1
            bill_last_touched_on[b] = dt
        for b, cnt in d.get('amendment_docs_by_bill', {}).items():
            bill_amend_counts[b] += cnt
            bill_last_touched_on[b] = dt
        for b in d['updated_fiscal_notes']:
            bill_fn_update_counts[b] += 1
            bill_last_touched_on[b] = dt

    # Most-modified bill
    top_modified = bill_mod_counts.most_common(5)
    # Most-amended bill (by amendment doc count)
    top_amended = bill_amend_counts.most_common(5)
    # Most FN-updated bill
    top_fn_updated = bill_fn_update_counts.most_common(5)

    # Longest active bill (days between introduction and last touch)
    longest_active = None
    longest_span = 0
    for b, intro in bill_introduced_on.items():
        last = bill_last_touched_on.get(b, intro)
        span = (datetime.strptime(last, '%Y-%m-%d') - datetime.strptime(intro, '%Y-%m-%d')).days
        if span > longest_span:
            longest_span = span
            longest_active = (b, intro, last, span)

    # Bill with most total "events" (modifications + amendments + fn updates)
    all_bills_seen = (set(bill_mod_counts.keys()) |
                      set(bill_amend_counts.keys()) |
                      set(bill_fn_update_counts.keys()))
    bill_total_events = {
        b: bill_mod_counts[b] + bill_amend_counts[b] + bill_fn_update_counts[b]
        for b in all_bills_seen
    }
    top_overall = Counter(bill_total_events).most_common(5)

    # Longest / shortest bills (by word count of main .md file)
    md_dir = os.path.join(REPO_PATH, f'data/2026rs/md')
    bill_word_counts = {}
    for fname in os.listdir(md_dir):
        if not re.match(r'^[HS]B\d+\.md$', fname):
            continue
        fpath = os.path.join(md_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                text = fh.read()
            words = len(text.split())
            bill_num = fname.replace('.md', '')
            bill_word_counts[bill_num] = words
        except Exception:
            pass

    sorted_by_words = sorted(bill_word_counts.items(), key=lambda x: x[1], reverse=True)
    top5_longest = sorted_by_words[:5]
    top5_shortest = [x for x in reversed(sorted_by_words) if x[1] > 0][:5]

    MGA_BASE = 'https://mgaleg.maryland.gov/mgawebsite/Legislation/Details'

    def mga_url(bill):
        return f'{MGA_BASE}/{bill}?ys=2026rs'

    def fmt_date(ds):
        return datetime.strptime(ds, '%Y-%m-%d').strftime('%b %-d')

    def _subject_bars(entries, total_subjects, bar_color, label_color):
        rows = []
        max_count = entries[0][1] if entries else 1
        medals = ['🥇', '🥈', '🥉']
        for i, (name, count) in enumerate(entries):
            bar_pct = round(count / max_count * 100)
            bill_pct = round(count / total_session_bills * 100)
            rows.append(
                f'<div style="margin-bottom:1.1rem">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:0.35rem">'
                f'<span style="font-size:0.85rem;color:var(--text);font-family:\'Source Serif 4\',serif">'
                f'{medals[i]}&nbsp; {name}</span>'
                f'<span style="font-family:\'Courier Prime\',monospace;font-weight:700;'
                f'font-size:0.9rem;color:{label_color}">{count}'
                f'<span style="font-weight:400;font-size:0.72rem;color:var(--text-muted)"> bills ({bill_pct}%)</span></span>'
                f'</div>'
                f'<div style="height:6px;background:var(--surface);border-radius:3px;overflow:hidden">'
                f'<div style="height:100%;width:{bar_pct}%;background:{bar_color};'
                f'border-radius:3px;opacity:0.75;transition:width 0.6s ease"></div>'
                f'</div>'
                f'</div>'
            )
        return ''.join(rows)

    def podium_html(entries, color, extra_fn=None):
        medals = ['🥇', '🥈', '🥉', '4th', '5th']
        rows = []
        for i, (bill, cnt) in enumerate(entries):
            medal = medals[i] if i < 3 else medals[i]
            extra = extra_fn(bill, cnt) if extra_fn else ''
            rows.append(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:0.45rem 0;border-bottom:1px solid rgba(255,255,255,0.04)">'
                f'<span>{medal}&nbsp; '
                f'<a href="{mga_url(bill)}" target="_blank" rel="noopener" '
                f'style="font-family:\'Courier Prime\',monospace;font-size:0.85rem;color:{color};'
                f'text-decoration:none;border-bottom:1px dotted {color}" '
                f'onclick="event.stopPropagation()">{bill}</a>'
                f'{extra}</span>'
                f'<span style="font-family:\'Courier Prime\',monospace;font-weight:700;color:{color}">{cnt}</span>'
                f'</div>'
            )
        return ''.join(rows)

    data_json = json.dumps(daily_data)
    date_labels_json = json.dumps(date_labels)
    cum_bills_json = json.dumps(cum_bills)
    cum_amend_json = json.dumps(cum_amend)
    cum_fn_json = json.dumps(cum_fn)

    busiest_label = datetime.strptime(busiest['date'], '%Y-%m-%d').strftime('%B %-d')
    most_new_label = datetime.strptime(most_new_bills['date'], '%Y-%m-%d').strftime('%B %-d')
    most_amd_label = datetime.strptime(most_amendments['date'], '%Y-%m-%d').strftime('%B %-d')

    if longest_active:
        la_bill, la_intro, la_last, la_span = longest_active
        longest_active_html = (
            f'<div class="chart-card" style="margin-top:1rem">'
            f'<div class="chart-card-title" style="color:var(--gold)">Longest Active Bill</div>'
            f'<div style="display:flex;align-items:baseline;gap:1.5rem;flex-wrap:wrap">'
            f'<div><a href="{mga_url(la_bill)}" target="_blank" rel="noopener" '
            f'style="font-family:\'Courier Prime\',monospace;font-size:1.8rem;font-weight:700;'
            f'color:var(--gold-bright);text-decoration:none;border-bottom:2px solid var(--gold)">'
            f'{la_bill}</a></div>'
            f'<div style="font-size:0.9rem;color:var(--text-muted)">'
            f'First seen <span style="color:var(--text)">{fmt_date(la_intro)}</span> &middot; '
            f'Last touched <span style="color:var(--text)">{fmt_date(la_last)}</span> &middot; '
            f'<span style="color:var(--gold-bright);font-weight:700">{la_span} days</span> active'
            f'</div></div></div>'
        )
    else:
        longest_active_html = ''

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026 Maryland General Assembly — Session Report</title>
<!-- Maryland Web Design System (MDWDS) — matches main Legi-Assist site -->
<link rel="stylesheet" href="https://cdn.maryland.gov/mdwds/0.36.0/css/mdwds.min.css" />
<script src="https://cdn.maryland.gov/mdwds/0.36.0/js/mdwds-init.js"></script>
<script defer src="https://cdn.maryland.gov/mdwds/0.36.0/js/mdwds-core.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=Courier+Prime:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #080a0f;
    --surface: #10131b;
    --card: #161a25;
    --card-hover: #1c2130;
    --border: rgba(196, 155, 27, 0.18);
    --border-strong: rgba(196, 155, 27, 0.4);
    --gold: #c49b1b;
    --gold-bright: #e8be3c;
    --gold-dim: rgba(196, 155, 27, 0.6);
    --red: #b8202e;
    --red-bright: #e03545;
    --text: #e8e0cc;
    --text-muted: #8a8070;
    --text-dim: #7a7060;  /* raised from #4a4438 — WCAG AA 4.5:1 on --card bg */
    --green: #2d7a52;
    --green-bright: #3da86e;
    --blue: #2855a0;
    --blue-bright: #4a80e0;
    --amber: #c47b1b;
    --amber-bright: #e09a30;
    --new-bills: #e8be3c;
    --modified: #4a80e0;
    --amendments: #e03545;
    --fn-new: #3da86e;
    --fn-updated: #7b5ea0;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  html {{ scroll-behavior: smooth; }}

  /* ─── Skip nav (WCAG 2.4.1) ──────────────────────────────── */
  .skip-nav {{
    position: absolute;
    top: -9999px; left: -9999px;
    background: var(--gold-bright);
    color: var(--bg);
    padding: 0.75rem 1.5rem;
    font-family: 'Courier Prime', monospace;
    font-weight: 700;
    font-size: 0.9rem;
    z-index: 10000;
    text-decoration: none;
    border-radius: 0 0 4px 0;
  }}
  .skip-nav:focus {{
    top: 0; left: 0;
    outline: 3px solid var(--gold);
    outline-offset: 2px;
  }}


  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 16px;
    line-height: 1.6;
    min-height: 100vh;
    overflow-x: hidden;
  }}

  /* Grain overlay */
  body::before {{
    content: '';
    position: fixed;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 9999;
    opacity: 0.35;
  }}

  /* ─── Layout ─────────────────────────────────────────────── */
  .container {{
    max-width: 1300px;
    margin: 0 auto;
    padding: 0 2rem;
  }}

  /* ─── Header ──────────────────────────────────────────────── */
  .header-top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 2rem;
  }}

  .header-brand-link {{
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-top: 0.25rem;
    text-decoration: none;
    opacity: 0.9;
    transition: opacity 0.15s;
  }}

  .header-built-by {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-muted);
  }}
  .header {{
    border-bottom: 1px solid var(--border);
    padding: 3.5rem 0 2.5rem;
    position: relative;
    overflow: hidden;
  }}

  .header::after {{
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold), transparent);
  }}

  .header-rule {{
    width: 100%;
    height: 3px;
    background: repeating-linear-gradient(
      90deg,
      var(--gold) 0px,
      var(--gold) 40px,
      transparent 40px,
      transparent 44px
    );
    margin-bottom: 2.5rem;
    opacity: 0.5;
  }}

  .header-eyebrow {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }}

  .header-eyebrow::before,
  .header-eyebrow::after {{
    content: '◆';
    font-size: 0.5em;
    opacity: 0.6;
  }}

  h1 {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: clamp(2.2rem, 5vw, 4rem);
    font-weight: 900;
    line-height: 1.05;
    color: var(--text);
    letter-spacing: -0.02em;
  }}

  h1 em {{
    font-style: italic;
    color: var(--gold-bright);
  }}

  .header-meta {{
    display: flex;
    gap: 2rem;
    margin-top: 1.5rem;
    font-family: 'Courier Prime', monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
    flex-wrap: wrap;
  }}

  .header-meta span {{
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }}

  .header-meta .dot {{
    width: 5px; height: 5px;
    background: var(--gold);
    border-radius: 50%;
    display: inline-block;
  }}

  /* ─── Stats Row ───────────────────────────────────────────── */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin: 3rem 0;
    border-radius: 2px;
  }}

  .stat-cell {{
    background: var(--card);
    padding: 1.8rem 1.5rem;
    position: relative;
    transition: background 0.2s;
    cursor: default;
  }}

  .stat-cell:hover {{
    background: var(--card-hover);
  }}

  .stat-cell::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--accent, var(--gold));
    opacity: 0.7;
  }}

  .stat-label {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.6rem;
  }}

  .stat-number {{
    font-family: 'Courier Prime', monospace;
    font-size: 2.6rem;
    font-weight: 700;
    line-height: 1;
    color: var(--accent, var(--gold-bright));
    letter-spacing: -0.02em;
  }}

  .stat-sub {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.4rem;
    font-family: 'Source Serif 4', serif;
  }}

  /* ─── Section titles ──────────────────────────────────────── */
  .section {{
    margin: 3rem 0;
  }}

  .section-header {{
    display: flex;
    align-items: baseline;
    gap: 1.2rem;
    margin-bottom: 1.5rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
  }}

  h2 {{
    font-family: 'Playfair Display', serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.01em;
  }}

  .section-tag {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--gold);
    border: 1px solid var(--border-strong);
    padding: 0.2em 0.6em;
    border-radius: 1px;
  }}

  /* ─── Chart cards ─────────────────────────────────────────── */
  .chart-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 2px;
    padding: 1.5rem;
    position: relative;
  }}

  .chart-card-title {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 1.2rem;
  }}

  .chart-container {{
    position: relative;
    width: 100%;
    /* Prevents Chart.js canvas from expanding its grid cell */
    overflow: hidden;
  }}

  /* ─── Legend toggles ──────────────────────────────────────── */
  .legend-toggles {{
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
    margin-bottom: 1.2rem;
  }}

  .legend-btn {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.3em 0.8em;
    border-radius: 1px;
    border: 1px solid var(--btn-color, var(--border));
    background: transparent;
    color: var(--btn-color, var(--text-muted));
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 0.4em;
  }}

  .legend-btn::before {{
    content: '';
    width: 8px; height: 8px;
    border-radius: 1px;
    background: var(--btn-color);
    flex-shrink: 0;
  }}

  .legend-btn.active {{
    background: var(--btn-color);
    color: var(--bg);
    font-weight: 700;
  }}

  .legend-btn:hover:not(.active) {{
    background: rgba(255,255,255,0.05);
  }}

  /* ─── Two-col layout ──────────────────────────────────────── */
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
  }}

  /* ─── Three-col layout ────────────────────────────────────── */
  .three-col {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
  }}

  /* Grid children must be able to shrink below content min-width,
     otherwise a min-width:max-content heatmap or wide canvas will
     blow out the column and push everything else off-screen. */
  .two-col > *,
  .three-col > *,
  .stats-grid > *,
  .fun-stats > * {{
    min-width: 0;
  }}

  /* ─── Heatmap ─────────────────────────────────────────────── */
  .heatmap-wrap {{
    overflow-x: auto;
    padding-bottom: 0.5rem;
  }}

  .heatmap {{
    display: grid;
    grid-template-rows: auto repeat(7, 18px);
    grid-auto-flow: column;
    gap: 3px;
    min-width: max-content;
    align-items: start;
  }}

  .heatmap-day-label {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.6rem;
    color: var(--text-dim);
    text-align: right;
    padding-right: 6px;
    line-height: 18px;
  }}

  .heatmap-week-label {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.6rem;
    color: var(--text-dim);
    text-align: center;
    height: 18px;
    line-height: 18px;
  }}

  .heatmap-cell {{
    width: 18px; height: 18px;
    border-radius: 2px;
    background: var(--cell-color, var(--surface));
    border: 1px solid rgba(0,0,0,0.3);
    cursor: pointer;
    transition: transform 0.1s, filter 0.1s;
    position: relative;
  }}

  .heatmap-cell:hover {{
    transform: scale(1.3);
    filter: brightness(1.4);
    z-index: 10;
  }}

  .heatmap-cell.no-data {{
    opacity: 0.15;
    cursor: default;
  }}

  .heatmap-cell.no-data:hover {{
    transform: none;
    filter: none;
  }}

  /* ─── Fun stats ───────────────────────────────────────────── */
  .fun-stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
  }}

  .fun-stat-card {{
    background: var(--card);
    border: 1px solid var(--border);
    padding: 1.5rem;
    border-radius: 2px;
    position: relative;
    overflow: hidden;
  }}

  .fun-stat-card::after {{
    content: var(--icon, '');
    position: absolute;
    right: 1rem;
    bottom: 0.5rem;
    font-size: 3.5rem;
    opacity: 0.06;
    pointer-events: none;
    line-height: 1;
  }}

  .fun-stat-card .label {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }}

  .fun-stat-card .value {{
    font-family: 'Playfair Display', serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
    line-height: 1.2;
  }}

  .fun-stat-card .detail {{
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 0.4rem;
    font-family: 'Source Serif 4', serif;
  }}

  .highlight {{
    color: var(--gold-bright);
    font-weight: 700;
  }}

  /* ─── Day detail panel ────────────────────────────────────── */
  .detail-panel {{
    position: fixed;
    top: 0; right: 0;
    width: 380px;
    height: 100vh;
    background: var(--surface);
    border-left: 1px solid var(--border-strong);
    z-index: 100;
    transform: translateX(100%);
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}

  .detail-panel.open {{
    transform: translateX(0);
    box-shadow: -20px 0 60px rgba(0,0,0,0.6);
  }}

  .detail-header {{
    padding: 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    flex-shrink: 0;
  }}

  .detail-date {{
    font-family: 'Playfair Display', serif;
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--gold-bright);
  }}

  .detail-close {{
    background: none;
    border: 1px solid var(--border);
    color: var(--text-muted);
    width: 32px; height: 32px;
    border-radius: 1px;
    cursor: pointer;
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
    flex-shrink: 0;
    font-family: 'Courier Prime', monospace;
  }}

  .detail-close:hover {{
    border-color: var(--gold);
    color: var(--gold);
  }}

  .detail-body {{
    padding: 1rem 1.5rem;
    overflow-y: auto;
    flex: 1;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }}

  .detail-section {{
    margin-bottom: 1.5rem;
  }}

  .detail-section-title {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    padding: 0.3em 0;
    margin-bottom: 0.6rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .detail-section-title .count {{
    font-weight: 700;
    color: var(--gold);
  }}

  .bill-list {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }}

  .bill-tag {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.72rem;
    padding: 0.2em 0.5em;
    border: 1px solid var(--tag-color, var(--border));
    border-radius: 1px;
    color: var(--tag-color, var(--text-muted));
    background: rgba(255,255,255,0.02);
  }}

  .bill-tag:hover {{
    background: rgba(255,255,255,0.06);
  }}

  /* ─── Overlay ─────────────────────────────────────────────── */
  .overlay {{
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 99;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s;
  }}

  .overlay.visible {{
    opacity: 1;
    pointer-events: all;
  }}

  /* ─── Table ───────────────────────────────────────────────── */
  .table-scroll {{
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }}

  .data-table {{
    width: 100%;
    min-width: 560px; /* prevents columns collapsing before scroll kicks in */
    border-collapse: collapse;
    font-size: 0.85rem;
  }}

  .data-table th {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 0.7rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}

  .data-table th.num {{ text-align: right; }}

  .data-table td {{
    padding: 0.6rem 1rem;
    border-bottom: 1px solid rgba(196, 155, 27, 0.06);
    vertical-align: middle;
    font-family: 'Source Serif 4', serif;
  }}

  .data-table td.num {{
    text-align: right;
    font-family: 'Courier Prime', monospace;
    font-weight: 700;
  }}

  .data-table tr {{
    cursor: pointer;
    transition: background 0.1s;
  }}

  .data-table tr:hover td {{
    background: rgba(196, 155, 27, 0.04);
  }}

  .data-table .date-cell {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.85rem;
    color: var(--text-muted);
    white-space: nowrap;
  }}

  .data-table .manual-badge {{
    font-family: 'Courier Prime', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--amber);
    border: 1px solid var(--amber);
    padding: 0.1em 0.4em;
    border-radius: 1px;
    margin-left: 0.5rem;
    opacity: 0.8;
  }}

  .num-new {{ color: var(--new-bills); }}
  .num-mod {{ color: var(--modified); }}
  .num-amd {{ color: var(--amendments); }}
  .num-fn {{ color: var(--fn-new); }}
  .num-fnu {{ color: var(--fn-updated); }}

  .spark-bar {{
    display: inline-block;
    height: 8px;
    min-width: 2px;
    border-radius: 1px;
    vertical-align: middle;
    margin-right: 1px;
  }}

  /* ─── Footer ──────────────────────────────────────────────── */
  .footer {{
    border-top: 1px solid var(--border);
    padding: 2rem 0;
    margin-top: 4rem;
    display: flex;
    justify-content: center;
    align-items: center;
  }}

  /* ─── Animations ──────────────────────────────────────────── */
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  @keyframes countUp {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
  }}

  .animate-in {{
    animation: fadeUp 0.5s ease forwards;
    opacity: 0;
  }}

  .animate-in:nth-child(1) {{ animation-delay: 0.05s; }}
  .animate-in:nth-child(2) {{ animation-delay: 0.1s; }}
  .animate-in:nth-child(3) {{ animation-delay: 0.15s; }}
  .animate-in:nth-child(4) {{ animation-delay: 0.2s; }}
  .animate-in:nth-child(5) {{ animation-delay: 0.25s; }}

  /* ─── Tooltip ─────────────────────────────────────────────── */
  .heatmap-tooltip {{
    position: fixed;
    background: var(--card);
    border: 1px solid var(--border-strong);
    padding: 0.5rem 0.75rem;
    font-family: 'Courier Prime', monospace;
    font-size: 0.72rem;
    pointer-events: none;
    z-index: 1000;
    white-space: nowrap;
    display: none;
    color: var(--text);
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }}

  .heatmap-tooltip .tt-date {{ color: var(--gold); font-weight: 700; margin-bottom: 0.2em; }}
  .heatmap-tooltip .tt-row {{ color: var(--text-muted); }}
  .heatmap-tooltip .tt-row span {{ color: var(--text); }}

  @media (max-width: 900px) {{
    .stats-grid {{ grid-template-columns: repeat(3, 1fr); }}
    .two-col {{ grid-template-columns: 1fr; }}
    .three-col {{ grid-template-columns: 1fr 1fr; }}
    .fun-stats {{ grid-template-columns: 1fr 1fr; }}
    .detail-panel {{ width: 100%; }}
  }}

  @media (max-width: 600px) {{
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .three-col {{ grid-template-columns: 1fr; }}
    .fun-stats {{ grid-template-columns: 1fr; }}
    .stat-number {{ font-size: 2rem; }}
    .container {{ padding: 0 1rem; }}
    h1 {{ font-size: 2rem; }}
    .header-top {{ flex-direction: column; gap: 1rem; }}
    .header-brand-link {{ margin-top: 0; }}
  }}
</style>
</head>
<body>

<a href="#main-content" class="skip-nav">Skip to main content</a>

<!-- Heatmap tooltip — aria-hidden, mouse-only affordance -->
<div class="heatmap-tooltip" id="hmTooltip" role="tooltip" aria-hidden="true">
  <div class="tt-date" id="ttDate"></div>
  <div class="tt-row">New Bills: <span id="ttNew"></span></div>
  <div class="tt-row">Modified: <span id="ttMod"></span></div>
  <div class="tt-row">Amendments: <span id="ttAmd"></span></div>
  <div class="tt-row">Fiscal Notes: <span id="ttFn"></span></div>
</div>

<!-- Overlay -->
<div class="overlay" id="overlay" onclick="closePanel()" aria-hidden="true"></div>

<!-- Day detail panel -->
<aside
  class="detail-panel"
  id="detailPanel"
  role="dialog"
  aria-modal="true"
  aria-labelledby="dpDate"
  aria-hidden="true"
>
  <div class="detail-header">
    <div>
      <div class="detail-date" id="dpDate">—</div>
      <div style="font-family:'Courier Prime',monospace;font-size:0.7rem;color:var(--text-muted);margin-top:0.2rem;" id="dpLabel"></div>
    </div>
    <button class="detail-close" onclick="closePanel()" aria-label="Close day detail panel">✕</button>
  </div>
  <div class="detail-body" id="dpBody" tabindex="-1"></div>
</aside>

<main id="main-content" tabindex="-1">
<div class="container">

  <!-- Header -->
  <header class="header animate-in" style="animation-delay:0s;opacity:0">
    <div class="header-rule"></div>
    <div class="header-top">
      <div>
        <div class="header-eyebrow">Maryland General Assembly · 2026 Regular Session · Pipeline Analytics</div>
        <h1>The <em>Full Session</em><br>By the Numbers</h1>
      </div>
      <a href="https://innovation.maryland.gov" target="_blank" rel="noopener"
         class="header-brand-link"
         onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.9'"
      >
        <span class="header-built-by">Built by</span>
        <img src="assets/innovation-website-logo-light.png"
             alt="The Office of Governor Wes Moore Innovation Team"
             style="height:2.2rem;width:auto;">
        <span class="usa-sr-only">(opens in new tab)</span>
      </a>
    </div>
    <div class="header-meta">
      <span><span class="dot"></span> {num_runs} pipeline runs</span>
      <span><span class="dot"></span> {session_days} day span</span>
      <span><span class="dot"></span> {daily_data[0]['date']} — {daily_data[-1]['date']}</span>
      <span><span class="dot"></span> Sine Die: April 13, 2026</span>
    </div>
  </header>

  <!-- Stats row -->
  <div class="stats-grid" role="region" aria-label="Session summary statistics">
    <div class="stat-cell animate-in" style="--accent:var(--new-bills)">
      <div class="stat-label">Total Session Bills</div>
      <div class="stat-number" data-count="{total_session_bills}">0</div>
      <div class="stat-sub">{pre_pipeline_bills} before pipeline · {total_new_bills} tracked</div>
    </div>
    <div class="stat-cell animate-in" style="--accent:var(--modified)">
      <div class="stat-label">Bill Updates</div>
      <div class="stat-number" data-count="{total_modified}">0</div>
      <div class="stat-sub">text changes via pipeline</div>
    </div>
    <div class="stat-cell animate-in" style="--accent:var(--amendments)">
      <div class="stat-label">Amendments</div>
      <div class="stat-number" data-count="{total_amend_docs}">0</div>
      <div class="stat-sub">amendment documents filed</div>
    </div>
    <div class="stat-cell animate-in" style="--accent:var(--fn-new)">
      <div class="stat-label">New Fiscal Notes</div>
      <div class="stat-number" data-count="{total_fn_new}">0</div>
      <div class="stat-sub">fiscal analyses filed</div>
    </div>
    <div class="stat-cell animate-in" style="--accent:var(--fn-updated)">
      <div class="stat-label">FN Updates</div>
      <div class="stat-number" data-count="{total_fn_updated}">0</div>
      <div class="stat-sub">fiscal notes revised</div>
    </div>
  </div>

  <!-- Main daily chart -->
  <div class="section">
    <div class="section-header">
      <h2>Daily Legislative Activity</h2>
      <span class="section-tag">Click any bar for details</span>
    </div>
    <div class="chart-card">
      <div class="legend-toggles" id="mainLegend">
        <button class="legend-btn active" style="--btn-color:var(--new-bills)" data-series="0">New Bills</button>
        <button class="legend-btn active" style="--btn-color:var(--modified)" data-series="1">Modified</button>
        <button class="legend-btn active" style="--btn-color:var(--amendments)" data-series="2">Amendments</button>
        <button class="legend-btn active" style="--btn-color:var(--fn-new)" data-series="3">New FNs</button>
        <button class="legend-btn active" style="--btn-color:var(--fn-updated)" data-series="4">Updated FNs</button>
      </div>
      <div class="chart-container" style="height:340px">
        <canvas id="dailyChart"
          role="img"
          aria-label="Stacked bar chart of daily legislative activity: new bills, modifications, amendments, and fiscal notes from February to April 2026. Click any bar to see bill details for that day."
        ></canvas>
      </div>
    </div>
  </div>

  <!-- Heatmap + cumulative -->
  <div class="two-col section">
    <div>
      <div class="section-header">
        <h2>Activity Heatmap</h2>
        <span class="section-tag">Total events per day</span>
      </div>
      <div class="chart-card">
        <div class="legend-toggles" style="margin-bottom:1rem;">
          <span style="font-family:'Courier Prime',monospace;font-size:0.65rem;color:var(--text-muted);letter-spacing:0.1em;">LESS</span>
          <span style="display:inline-flex;gap:3px;margin:0 0.5rem;align-items:center;">
            <span style="width:14px;height:14px;background:#1c2130;border-radius:2px;display:inline-block;border:1px solid rgba(0,0,0,0.3)"></span>
            <span style="width:14px;height:14px;background:#2a3820;border-radius:2px;display:inline-block;border:1px solid rgba(0,0,0,0.3)"></span>
            <span style="width:14px;height:14px;background:#3a5c28;border-radius:2px;display:inline-block;border:1px solid rgba(0,0,0,0.3)"></span>
            <span style="width:14px;height:14px;background:#5a8c30;border-radius:2px;display:inline-block;border:1px solid rgba(0,0,0,0.3)"></span>
            <span style="width:14px;height:14px;background:#c49b1b;border-radius:2px;display:inline-block;border:1px solid rgba(0,0,0,0.3)"></span>
          </span>
          <span style="font-family:'Courier Prime',monospace;font-size:0.65rem;color:var(--text-muted);letter-spacing:0.1em;">MORE</span>
        </div>
        <div class="heatmap-wrap">
          <div class="heatmap" id="heatmap"></div>
        </div>
      </div>
    </div>

    <div>
      <div class="section-header">
        <h2>Cumulative Growth</h2>
        <span class="section-tag">Running totals</span>
      </div>
      <div class="chart-card">
        <div class="chart-container" style="height:260px">
          <canvas id="cumulativeChart"
            role="img"
            aria-label="Line chart showing cumulative growth of bills, amendments, and fiscal notes over the 2026 session. Bills start from the pre-pipeline baseline of {pre_pipeline_bills} on January 14."
          ></canvas>
        </div>
      </div>
    </div>
  </div>

  <!-- Fun stats -->
  <div class="section">
    <div class="section-header">
      <h2>Session Highlights</h2>
      <span class="section-tag">Notable moments</span>
    </div>
    <div class="fun-stats">
      <div class="fun-stat-card" style="--icon:'🔥'">
        <div class="label">Busiest Single Day</div>
        <div class="value">{busiest_label}</div>
        <div class="detail"><span class="highlight">{day_activity(busiest)}</span> total events — {busiest['new_bills_count']} new · {busiest['modified_bills_count']} modified · {busiest['amendment_docs_count']} amendments</div>
      </div>
      <div class="fun-stat-card" style="--icon:'📋'">
        <div class="label">Most New Bills in a Day</div>
        <div class="value">{most_new_label}</div>
        <div class="detail"><span class="highlight">{most_new_bills['new_bills_count']}</span> new bills introduced</div>
      </div>
      <div class="fun-stat-card" style="--icon:'✏️'">
        <div class="label">Peak Amendment Day</div>
        <div class="value">{most_amd_label}</div>
        <div class="detail"><span class="highlight">{most_amendments['amendment_docs_count']}</span> amendment documents filed in one day</div>
      </div>
      <div class="fun-stat-card" style="--icon:'⚡'">
        <div class="label">Sine Die Sprint</div>
        <div class="value">{sprint_pct_amend}% of amendments</div>
        <div class="detail">…filed in the final 2 weeks of session as session end neared. Fiscal note activity: <span class="highlight">{sprint_pct_fn}%</span> in the same window.</div>
      </div>
      <div class="fun-stat-card" style="--icon:'📅'">
        <div class="label">First Pipeline Run</div>
        <div class="value">{datetime.strptime(daily_data[0]['date'], '%Y-%m-%d').strftime('%B %-d')}</div>
        <div class="detail">First bill tracked: <span class="highlight">{daily_data[0]['new_bills'][0] if daily_data[0]['new_bills'] else 'n/a'}</span></div>
      </div>
      <div class="fun-stat-card" style="--icon:'🏁'">
        <div class="label">Last Day of Session</div>
        <div class="value">April 13, 2026</div>
        <div class="detail">Sine Die — <span class="highlight">{total_session_bills}</span> bills introduced, <span class="highlight">{total_amend_docs}</span> amendments filed across the session</div>
      </div>
    </div>
  </div>

  <!-- Session subjects -->
  <div class="section">
    <div class="section-header">
      <h2>Top Session Subjects</h2>
      <span class="section-tag">By bill count</span>
    </div>
    <div class="two-col">

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--gold)">Broad Subjects</div>
        <div style="margin-top:0.5rem">
          {_subject_bars(top3_broad, broad_counts.total(), 'var(--gold)', 'var(--gold-bright)')}
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--blue-bright)">Narrow Subjects</div>
        <div style="margin-top:0.5rem">
          {_subject_bars(top3_narrow, narrow_counts.total(), 'var(--blue-bright)', 'var(--blue-bright)')}
        </div>
      </div>

    </div>
  </div>

  <!-- Bill superlatives -->
  <div class="section">
    <div class="section-header">
      <h2>Bill Superlatives</h2>
      <span class="section-tag">Across the full session</span>
    </div>
    <div class="three-col">

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--amendments)">Most Amended Bill</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.8rem;font-style:italic">Total amendment documents filed</div>
        {podium_html(top_amended, 'var(--amendments)')}
      </div>

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--fn-updated)">Most Fiscal Note Updates</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.8rem;font-style:italic">Times the fiscal note was revised</div>
        {podium_html(top_fn_updated, 'var(--fn-updated)')}
      </div>

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--gold)">Most Active Overall</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.8rem;font-style:italic">Modifications + amendments + FN updates</div>
        {podium_html(top_overall, 'var(--gold-bright)')}
      </div>

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--new-bills)">Longest Bills (by word count)</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.8rem;font-style:italic">Most words in the bill text</div>
        {podium_html([(b, f'{c:,} words') for b, c in top5_longest], 'var(--new-bills)')}
      </div>

      <div class="chart-card">
        <div class="chart-card-title" style="color:var(--green-bright)">Shortest Bills (by word count)</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.8rem;font-style:italic">Most concise bill texts</div>
        {podium_html([(b, f'{c:,} words') for b, c in top5_shortest], 'var(--green-bright)')}
      </div>

    </div>
    {longest_active_html}
  </div>

  <!-- Day-by-day table -->
  <div class="section">
    <div class="section-header">
      <h2>Day-by-Day Breakdown</h2>
      <span class="section-tag">Click any row for bill details</span>
    </div>
    <div class="chart-card" style="padding:0">
      <div class="table-scroll">
      <table class="data-table" id="dataTable">
        <thead>
          <tr>
            <th>Date</th>
            <th>Activity</th>
            <th class="num" style="color:var(--new-bills)">New Bills</th>
            <th class="num" style="color:var(--modified)">Modified</th>
            <th class="num" style="color:var(--amendments)">Amendments</th>
            <th class="num" style="color:var(--fn-new)">New FNs</th>
            <th class="num" style="color:var(--fn-updated)">Upd. FNs</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
      </div>
    </div>
  </div>

  <footer class="footer" role="contentinfo">
    <div style="position:relative;overflow:hidden;padding:1rem 1.25rem;
                border:1px solid var(--border);background:var(--card);border-radius:2px;
                min-width:260px;">
      <img src="assets/logomark.svg" alt="" aria-hidden="true"
           style="position:absolute;top:50%;right:-20%;width:100%;
                  transform:translateY(-50%);opacity:0.07;
                  filter:invert(1) sepia(1) saturate(3) hue-rotate(5deg);
                  pointer-events:none;">
      <div style="position:relative">
        <p style="font-family:'Courier Prime',monospace;font-size:0.6rem;letter-spacing:0.2em;
                  text-transform:uppercase;color:var(--text-muted);margin:0 0 0.3rem;">Built by</p>
        <p style="font-family:'Playfair Display',serif;font-size:0.95rem;font-weight:700;
                  color:var(--text);margin:0 0 0.6rem;line-height:1.2;">
          The Maryland State<br>Innovation Team
        </p>
        <a href="https://innovation.maryland.gov" target="_blank" rel="noopener"
           style="font-family:'Courier Prime',monospace;font-size:0.65rem;letter-spacing:0.1em;
                  text-transform:uppercase;color:var(--gold);text-decoration:none;
                  border-bottom:1px solid var(--border-strong);padding-bottom:1px;
                  transition:color 0.15s,border-color 0.15s;"
           onmouseover="this.style.color='var(--gold-bright)';this.style.borderColor='var(--gold-bright)'"
           onmouseout="this.style.color='var(--gold)';this.style.borderColor='var(--border-strong)'"
        >Visit website <span aria-hidden="true">→</span><span class="usa-sr-only"> of the Maryland State Innovation Team (opens in new tab)</span></a>
      </div>
    </div>
  </footer>

</div><!-- /container -->
</main>

<script>
const DATA = {data_json};
const DATE_LABELS = {date_labels_json};
const CUM_BILLS = {cum_bills_json};
const CUM_AMEND = {cum_amend_json};
const CUM_FN = {cum_fn_json};

// ─── Animated counters ──────────────────────────────────────
function animateCount(el, target) {{
  const duration = 1200;
  const start = performance.now();
  const update = (now) => {{
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(eased * target).toLocaleString();
    if (progress < 1) requestAnimationFrame(update);
  }};
  requestAnimationFrame(update);
}}

const observer = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      const els = document.querySelectorAll('[data-count]');
      els.forEach(el => {{
        animateCount(el, +el.dataset.count);
        el.removeAttribute('data-count');
      }});
      observer.disconnect();
    }}
  }});
}}, {{ threshold: 0.3 }});
observer.observe(document.querySelector('.stats-grid'));

// ─── Chart defaults ──────────────────────────────────────────
Chart.defaults.color = '#8a8070';
Chart.defaults.borderColor = 'rgba(196,155,27,0.1)';
Chart.defaults.font.family = "'Courier Prime', monospace";

// ─── Daily bar chart ─────────────────────────────────────────
const dailyCtx = document.getElementById('dailyChart').getContext('2d');

const dailySeries = [
  {{ label:'New Bills', key:'new_bills_count', color:'rgba(232,190,60,0.85)' }},
  {{ label:'Modified', key:'modified_bills_count', color:'rgba(74,128,224,0.85)' }},
  {{ label:'Amendments', key:'amendment_docs_count', color:'rgba(224,53,69,0.85)' }},
  {{ label:'New FNs', key:'new_fiscal_notes_count', color:'rgba(61,168,110,0.85)' }},
  {{ label:'Updated FNs', key:'updated_fiscal_notes_count', color:'rgba(123,94,160,0.85)' }},
];

const dailyChart = new Chart(dailyCtx, {{
  type: 'bar',
  data: {{
    labels: DATE_LABELS,
    datasets: dailySeries.map(s => ({{
      label: s.label,
      data: DATA.map(d => d[s.key]),
      backgroundColor: s.color,
      borderColor: 'transparent',
      borderRadius: 2,
      borderSkipped: false,
    }}))
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#161a25',
        borderColor: 'rgba(196,155,27,0.3)',
        borderWidth: 1,
        titleColor: '#e8be3c',
        bodyColor: '#e8e0cc',
        padding: 12,
        callbacks: {{
          title: (items) => {{
            const d = DATA[items[0].dataIndex];
            return d.date;
          }}
        }}
      }},
    }},
    scales: {{
      x: {{
        stacked: true,
        grid: {{ display: false }},
        ticks: {{
          maxRotation: 45,
          font: {{ size: 9 }},
          maxTicksLimit: 20,
        }},
      }},
      y: {{
        stacked: true,
        grid: {{ color: 'rgba(196,155,27,0.07)' }},
        ticks: {{ font: {{ size: 9 }} }},
      }},
    }},
    onClick: (evt, elements) => {{
      if (elements.length) openPanel(DATA[elements[0].index]);
    }},
    animation: {{
      duration: 900,
      easing: 'easeOutQuart',
    }},
  }}
}});

// Toggle legend buttons
document.getElementById('mainLegend').querySelectorAll('.legend-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const idx = +btn.dataset.series;
    const meta = dailyChart.getDatasetMeta(idx);
    meta.hidden = !meta.hidden;
    btn.classList.toggle('active');
    dailyChart.update();
  }});
}});

// ─── Cumulative chart ────────────────────────────────────────
const cumCtx = document.getElementById('cumulativeChart').getContext('2d');
new Chart(cumCtx, {{
  type: 'line',
  data: {{
    labels: DATE_LABELS,
    datasets: [
      {{
        label: 'Bills',
        data: CUM_BILLS,
        borderColor: '#e8be3c',
        backgroundColor: 'rgba(232,190,60,0.08)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 5,
        borderWidth: 2,
      }},
      {{
        label: 'Amendments',
        data: CUM_AMEND,
        borderColor: '#e03545',
        backgroundColor: 'rgba(224,53,69,0.06)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 5,
        borderWidth: 2,
      }},
      {{
        label: 'New Fiscal Notes',
        data: CUM_FN,
        borderColor: '#3da86e',
        backgroundColor: 'rgba(61,168,110,0.06)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 5,
        borderWidth: 2,
      }},
    ],
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{
        display: true,
        position: 'top',
        labels: {{
          boxWidth: 12,
          boxHeight: 12,
          font: {{ size: 9 }},
          padding: 16,
          usePointStyle: true,
        }},
      }},
      tooltip: {{
        backgroundColor: '#161a25',
        borderColor: 'rgba(196,155,27,0.3)',
        borderWidth: 1,
        titleColor: '#e8be3c',
        bodyColor: '#e8e0cc',
        padding: 10,
      }},
    }},
    scales: {{
      x: {{
        grid: {{ display: false }},
        ticks: {{ font: {{ size: 8 }}, maxTicksLimit: 12, maxRotation: 0 }},
      }},
      y: {{
        grid: {{ color: 'rgba(196,155,27,0.07)' }},
        ticks: {{ font: {{ size: 8 }} }},
      }},
    }},
    animation: {{ duration: 1200, easing: 'easeOutQuart' }},
  }}
}});

// ─── Heatmap ─────────────────────────────────────────────────
(function buildHeatmap() {{
  const container = document.getElementById('heatmap');
  const tooltip = document.getElementById('hmTooltip');

  // Build a map of date → data
  const byDate = {{}};
  DATA.forEach(d => {{ byDate[d.date] = d; }});

  const totalActivity = d => d.new_bills_count + d.modified_bills_count +
    d.amendment_docs_count + d.new_fiscal_notes_count + d.updated_fiscal_notes_count;
  const maxActivity = Math.max(...DATA.map(totalActivity));

  function colorForActivity(n) {{
    if (n === 0) return '#1c2130';
    const t = n / maxActivity;
    if (t < 0.2) return '#2a3820';
    if (t < 0.4) return '#3a5c28';
    if (t < 0.65) return '#5a8c30';
    if (t < 0.85) return '#a0b428';
    return '#c49b1b';
  }}

  // Find start of first week containing first date
  const firstDate = new Date(DATA[0].date + 'T00:00:00');
  const lastDate = new Date(DATA[DATA.length - 1].date + 'T00:00:00');
  const gridStart = new Date(firstDate);
  gridStart.setDate(gridStart.getDate() - gridStart.getDay()); // back to Sunday

  const days = ['S','M','T','W','T','F','S'];

  // Column headers (week labels) — we'll add them as we go
  const weeks = [];
  let cur = new Date(gridStart);
  while (cur <= lastDate) {{
    weeks.push(new Date(cur));
    cur.setDate(cur.getDate() + 7);
  }}

  // Set grid columns
  container.style.gridTemplateColumns = `20px repeat(${{weeks.length}}, 18px)`;

  // Row 0: week labels (month labels)
  const emptyCorner = document.createElement('div');
  container.appendChild(emptyCorner);
  let lastMonth = -1;
  weeks.forEach(weekStart => {{
    const label = document.createElement('div');
    label.className = 'heatmap-week-label';
    const m = weekStart.getMonth();
    if (m !== lastMonth) {{
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      label.textContent = months[m];
      lastMonth = m;
    }}
    container.appendChild(label);
  }});

  // Rows 1–7: day labels + cells
  days.forEach((dayName, dayIdx) => {{
    const label = document.createElement('div');
    label.className = 'heatmap-day-label';
    label.textContent = dayName;
    container.appendChild(label);

    weeks.forEach(weekStart => {{
      const cellDate = new Date(weekStart);
      cellDate.setDate(cellDate.getDate() + dayIdx);
      const dateStr = cellDate.toISOString().split('T')[0];

      const cell = document.createElement('div');
      cell.className = 'heatmap-cell';

      const d = byDate[dateStr];
      if (!d) {{
        cell.classList.add('no-data');
        cell.style.setProperty('--cell-color', '#1c2130');
        cell.style.opacity = '0.2';
        cell.setAttribute('aria-hidden', 'true');
      }} else {{
        const activity = totalActivity(d);
        cell.style.setProperty('--cell-color', colorForActivity(activity));
        // Accessible label for keyboard/screen-reader users
        cell.setAttribute('tabindex', '0');
        cell.setAttribute('role', 'button');
        cell.setAttribute('aria-label',
          `${{d.date}}: ${{d.new_bills_count}} new bills, ${{d.modified_bills_count}} modified, ` +
          `${{d.amendment_docs_count}} amendments, ${{d.new_fiscal_notes_count}} new fiscal notes`
        );
        cell.addEventListener('mouseenter', (e) => {{
          tooltip.style.display = 'block';
          document.getElementById('ttDate').textContent = d.date;
          document.getElementById('ttNew').textContent = d.new_bills_count;
          document.getElementById('ttMod').textContent = d.modified_bills_count;
          document.getElementById('ttAmd').textContent = d.amendment_docs_count;
          document.getElementById('ttFn').textContent = d.new_fiscal_notes_count + ' new · ' + d.updated_fiscal_notes_count + ' updated';
          positionTooltip(e);
        }});
        cell.addEventListener('mousemove', positionTooltip);
        cell.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none'; }});
        cell.addEventListener('click', () => openPanel(d));
        cell.addEventListener('keydown', (e) => {{
          if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); openPanel(d); }}
        }});
      }}
      container.appendChild(cell);
    }});
  }});

  function positionTooltip(e) {{
    const x = e.clientX + 14, y = e.clientY + 14;
    tooltip.style.left = Math.min(x, window.innerWidth - 200) + 'px';
    tooltip.style.top = y + 'px';
  }}
}})();

// ─── Table ───────────────────────────────────────────────────
(function buildTable() {{
  const tbody = document.getElementById('tableBody');
  const maxTotal = Math.max(...DATA.map(d =>
    d.new_bills_count + d.modified_bills_count + d.amendment_docs_count +
    d.new_fiscal_notes_count + d.updated_fiscal_notes_count
  ));

  DATA.slice().reverse().forEach(d => {{
    const tr = document.createElement('tr');
    tr.addEventListener('click', () => openPanel(d));

    const dateLabel = new Date(d.date + 'T12:00:00').toLocaleDateString('en-US', {{
      weekday: 'short', month: 'short', day: 'numeric'
    }});

    const total = d.new_bills_count + d.modified_bills_count + d.amendment_docs_count +
      d.new_fiscal_notes_count + d.updated_fiscal_notes_count;
    const barW = Math.round(total / maxTotal * 80);

    tr.innerHTML = `
      <td class="date-cell">${{dateLabel}}</td>
      <td>
        <span class="spark-bar" style="width:${{barW}}px;background:linear-gradient(90deg,rgba(232,190,60,0.6),rgba(196,155,27,0.3))"></span>
        <span style="font-family:'Courier Prime',monospace;font-size:0.72rem;color:var(--text-muted)">${{total}}</span>
      </td>
      <td class="num num-new">${{d.new_bills_count || '—'}}</td>
      <td class="num num-mod">${{d.modified_bills_count || '—'}}</td>
      <td class="num num-amd">${{d.amendment_docs_count || '—'}}</td>
      <td class="num num-fn">${{d.new_fiscal_notes_count || '—'}}</td>
      <td class="num num-fnu">${{d.updated_fiscal_notes_count || '—'}}</td>
    `;
    tbody.appendChild(tr);
  }});
}})();

// ─── Detail panel ────────────────────────────────────────────
function openPanel(d) {{
  const panel = document.getElementById('detailPanel');
  const overlay = document.getElementById('overlay');

  document.getElementById('dpDate').textContent =
    new Date(d.date + 'T12:00:00').toLocaleDateString('en-US', {{
      weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
    }});
  document.getElementById('dpLabel').textContent = d.label;

  const body = document.getElementById('dpBody');
  body.innerHTML = '';

  function makeSection(title, bills, color, key) {{
    if (!bills || bills.length === 0) return;
    const sec = document.createElement('div');
    sec.className = 'detail-section';
    sec.innerHTML = `
      <div class="detail-section-title" style="color:${{color}}">
        ${{title}} <span class="count">${{bills.length}}</span>
      </div>
      <div class="bill-list">${{
        bills.map(b => `<a href="https://mgaleg.maryland.gov/mgawebsite/Legislation/Details/${{b}}?ys=2026rs" target="_blank" rel="noopener" class="bill-tag" style="--tag-color:${{color}};text-decoration:none">${{b}}</a>`).join('')
      }}</div>
    `;
    body.appendChild(sec);
  }}

  makeSection('New Bills Introduced', d.new_bills, 'var(--new-bills)');
  makeSection('Bills Modified', d.modified_bills, 'var(--modified)');
  makeSection('Bills Receiving Amendments', d.amended_bills, 'var(--amendments)');
  makeSection('New Fiscal Notes', d.new_fiscal_notes, 'var(--fn-new)');
  makeSection('Updated Fiscal Notes', d.updated_fiscal_notes, 'var(--fn-updated)');

  if (!body.children.length) {{
    body.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:1rem 0">No bill-level changes recorded for this run.</div>';
  }}

  panel.classList.add('open');
  panel.setAttribute('aria-hidden', 'false');
  overlay.classList.add('visible');
  overlay.setAttribute('aria-hidden', 'true'); // overlay itself stays hidden to AT

  // Move focus into panel for keyboard/screen-reader users (WCAG 2.4.3)
  const closeBtn = panel.querySelector('.detail-close');
  if (closeBtn) closeBtn.focus();

  // Trap focus within panel while open
  panel._prevFocus = document.activeElement;
}}

function closePanel() {{
  const panel = document.getElementById('detailPanel');
  panel.classList.remove('open');
  panel.setAttribute('aria-hidden', 'true');
  document.getElementById('overlay').classList.remove('visible');
  // Restore focus to element that triggered the panel (WCAG 2.4.3)
  if (panel._prevFocus) panel._prevFocus.focus();
}}

document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closePanel();
}});
</script>
</body>
</html>"""

    return html


def main():
    print("Fetching pipeline commits...")
    commits = get_pipeline_commits()
    print(f"Found {len(commits)} pipeline runs")

    daily_data = []
    for commit in commits:
        print(f"  Analyzing {commit['date']} ({commit['hash'][:8]})...")
        analysis = analyze_commit(commit['hash'])
        daily_data.append({
            'date': commit['date'],
            'label': commit['label'],
            'is_manual': commit['is_manual'],
            'hash': commit['hash'][:8],
            **analysis,
        })

    print("\nBuilding HTML report...")
    html = build_html(daily_data)

    output_path = os.path.join(REPO_PATH, 'session_report_2026.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report saved to {output_path}")

    print(f"\n=== Summary ===")
    print(f"Pipeline runs:           {len(daily_data)}")
    print(f"Total new bills:         {sum(d['new_bills_count'] for d in daily_data)}")
    print(f"Total modifications:     {sum(d['modified_bills_count'] for d in daily_data)}")
    print(f"Total amendment docs:    {sum(d['amendment_docs_count'] for d in daily_data)}")
    print(f"Total new fiscal notes:  {sum(d['new_fiscal_notes_count'] for d in daily_data)}")
    print(f"Total updated FNs:       {sum(d['updated_fiscal_notes_count'] for d in daily_data)}")


if __name__ == '__main__':
    main()
