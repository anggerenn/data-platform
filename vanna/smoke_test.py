#!/usr/bin/env python3
"""
Vanna smoke test — run after any deployment to verify all intents + dashboard flow.

Usage:
    python vanna/smoke_test.py [--url http://localhost:8084] [--skip-dashboard]

Standard test inputs (reproducible):
  T1 — explore + chart:  "show me total revenue by city for march 2026"
  T2 — semantic:         "what does month over month growth mean?"
  T3 — explore → DPM → build dashboard (fixed answers)
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

# ── Fixed test inputs (same every run for reproducibility) ────────────────────

CHAT_TESTS = [
    # T1: explore — bar chart, Save Dashboard button
    {
        "label": "T1  explore: revenue by city march 2026",
        "question": "show me total revenue by city for march 2026",
        "intent": "explore",
        "checks": ["sql_present", "rows_gt_0", "chart_spec"],
    },
    # T2: semantic — no chart, no Save Dashboard
    {
        "label": "T2  semantic: mom growth definition",
        "question": "what does month over month growth mean?",
        "intent": "semantic",
        "checks": ["text_present", "no_sql"],
    },
    # Additional coverage
    {
        "label": "    explore: daily revenue trend by city",
        "question": "show me daily revenue trend by city for march 2026",
        "intent": "explore",
        "checks": ["sql_present", "rows_gt_0"],
    },
    {
        "label": "    explore: category performance march",
        "question": "give me the category performance for march 2026",
        "intent": "explore",
        "checks": ["sql_present", "rows_gt_0"],
    },
    {
        "label": "    semantic: what is daily_sales",
        "question": "What does the daily_sales table contain?",
        "intent": "semantic",
        "checks": ["text_present"],
    },
    {
        "label": "    clarify: ambiguous input",
        "question": "test",
        "intent": "clarify",
        "checks": ["text_present"],
    },
]

# T3: fixed DPM answers (in order, one per question)
DPM_EXPLORE_Q = "show me daily revenue trend by city for march 2026"
DPM_ANSWERS = [
    "we dont know which city is underperforming until its too late",
    "monitor daily revenue by city to catch drops early",
    "sales managers",
    "daily revenue per city, mom growth, category breakdown",
    "investigate underperforming city and reallocate resources",
]


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def post(url, payload, timeout=90):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        return None, f"HTTP {e.code}: {body[:200]}"
    except Exception as exc:
        return None, str(exc)


# ── Test runners ───────────────────────────────────────────────────────────────

def run_chat_tests(base_url):
    chat_url = f"{base_url}/chat"
    session_id = None
    passed = failed = 0

    print(f"\n── Chat tests {'─'*46}")
    for t in CHAT_TESTS:
        body = {"message": t["question"]}
        if session_id:
            body["session_id"] = session_id

        result, err = post(chat_url, body)
        if err:
            print(f"  ERROR  {t['label']}: {err}")
            failed += 1
            continue

        session_id = result.get("session_id", session_id)
        errors = []

        if result.get("intent") != t["intent"]:
            errors.append(f"intent={result.get('intent')!r}, want {t['intent']!r}")
        for check in t.get("checks", []):
            if check == "sql_present" and not result.get("sql"):
                errors.append("no SQL")
            elif check == "no_sql" and result.get("sql"):
                errors.append("unexpected SQL")
            elif check == "rows_gt_0" and not (result.get("row_count") or 0) > 0:
                errors.append(f"row_count={result.get('row_count')}")
            elif check == "text_present" and not (result.get("text") or "").strip():
                errors.append("empty text")
            elif check == "chart_spec" and not result.get("chart_spec"):
                errors.append("no chart_spec")

        if errors:
            print(f"  FAIL   {t['label']}")
            for e in errors:
                print(f"         - {e}")
            failed += 1
        else:
            print(f"  PASS   {t['label']}")
            passed += 1

    return passed, failed, session_id


def run_dashboard_test(base_url):
    passed = failed = 0
    print(f"\n── T3  Dashboard flow {'─'*39}")

    # Step 1: explore (fresh session)
    result, err = post(f"{base_url}/chat", {"message": DPM_EXPLORE_Q})
    if err or not result or result.get("intent") != "explore":
        print(f"  FAIL   explore step: {err or result.get('intent')}")
        return 0, 1
    session_id = result["session_id"]
    print(f"  PASS   explore → session {session_id[:8]}…")

    # Step 2: /dashboard/start
    result, err = post(f"{base_url}/dashboard/start", {"session_id": session_id})
    if err or not result or result.get("error"):
        print(f"  FAIL   /dashboard/start: {err or result.get('error')}")
        return 0, 1
    dpm_session_id = result["dpm_session_id"]
    print(f"  PASS   /dashboard/start → dpm {dpm_session_id[:8]}…")

    # Step 3: fixed DPM answers
    for i, answer in enumerate(DPM_ANSWERS):
        result, err = post(f"{base_url}/dashboard/chat", {
            "dpm_session_id": dpm_session_id,
            "message": answer,
        })
        if err or not result or result.get("error"):
            print(f"  FAIL   DPM answer {i+1}: {err or result.get('error')}")
            return 0, 1
        if result.get("status") == "complete":
            prd = result.get("prd") or {}
            print(f"  PASS   DPM complete (answer {i+1}) — {prd.get('title', '?')!r}")
            break
        print(f"  PASS   DPM answer {i+1} → clarifying")
    else:
        print("  FAIL   DPM never reached complete after 5 answers")
        return 0, 1

    # Step 4: /dashboard/build
    result, err = post(f"{base_url}/dashboard/build",
                       {"dpm_session_id": dpm_session_id}, timeout=120)
    if err or not result:
        print(f"  FAIL   /dashboard/build: {err}")
        return 0, 1
    if result.get("error"):
        print(f"  FAIL   /dashboard/build: {result['error']}")
        if result.get("yaml_written"):
            print(f"         yaml written: {result['yaml_written']}")
        return 0, 1

    print(f"  PASS   /dashboard/build → {result.get('charts_created', 0)} charts")
    print(f"         yaml: {result.get('yaml_written', '')}")
    print(f"         url:  {result.get('url', '')}")
    passed += 1
    return passed, failed


# ── Main ───────────────────────────────────────────────────────────────────────

def run(base_url, skip_dashboard=False):
    print(f"\nVanna smoke test  →  {base_url}")
    print("=" * 60)

    total_passed = total_failed = 0

    chat_passed, chat_failed, _ = run_chat_tests(base_url)
    total_passed += chat_passed
    total_failed += chat_failed

    if not skip_dashboard:
        db_passed, db_failed = run_dashboard_test(base_url)
        total_passed += db_passed
        total_failed += db_failed

    print(f"\n{'='*60}")
    print(f"Results: {total_passed} passed, {total_failed} failed")
    return total_failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8084")
    parser.add_argument("--skip-dashboard", action="store_true",
                        help="Skip the DPM → build dashboard test (faster)")
    args = parser.parse_args()

    ok = run(args.url, skip_dashboard=args.skip_dashboard)
    sys.exit(0 if ok else 1)
