import json
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

SEEN_FILE = Path("seen.json")

GOOGLE_ALERT_RSS_FEEDS = [
        "https://www.google.com/alerts/feeds/14816270209271166100/18014102174977099288"

]

SEC_RECENT_8K_RSS = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=100&output=atom"

ROLE_WORDS = [
    "ceo", "cfo", "coo", "cto",
    "chief executive officer",
    "chief financial officer",
    "chief operating officer",
    "chief technology officer",
    "president",
    "chair",
    "chairman",
    "board",
    "director",
]
BLOCKED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
]

EVENT_WORDS = [
    "resigns",
    "resigned",
    "steps down",
    "stepped down",
    "appointed",
    "named",
    "elected",
    "retires",
    "retired",
    "terminated",
    "departure",
    "succession",
    "joins",
    "promoted",
]


def load_seen():
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def is_blocked_link(link):
    return any(domain in link.lower() for domain in BLOCKED_DOMAINS)

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen)), f, indent=2)

def is_recent(published_str, hours=24):
    try:
        published = datetime.strptime(
            published_str,
            "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        return published >= cutoff

    except Exception:
        return False


def is_relevant(text):
    text = text.lower()
    has_role = any(word in text for word in ROLE_WORDS)
    has_event = any(word in text for word in EVENT_WORDS)
    return has_role and has_event


def get_google_alert_items():
    items = []

    for feed_url in GOOGLE_ALERT_RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            published = entry.get("published", "")

            combined_text = f"{title} {summary}"

            if (
                is_relevant(combined_text)
                and not is_blocked_link(link)
                and is_recent(published)
                ):
                items.append({
                    "source": "Google Alerts",
                    "title": BeautifulSoup(title, "html.parser").get_text(),
                    "link": link,
                    "published": published,
                    "summary": BeautifulSoup(summary, "html.parser").get_text(),
                })

    return items


def get_sec_8k_items():
    headers = {
        "User-Agent": "ExecutiveChangeAlertBot/1.0 emily.charles.2004@gmail.com"
    }

    response = requests.get(SEC_RECENT_8K_RSS, headers=headers, timeout=20)
    response.raise_for_status()

    feed = feedparser.parse(response.text)
    items = []

    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        summary = entry.get("summary", "")
        published = entry.get("updated", "")

        combined_text = f"{title} {summary}"

        # SEC RSS title/summary usually won't say Item 5.02,
        # so we keep broad 8-Ks that mention executive-related keywords.
        if is_relevant(combined_text):
            items.append({
                "source": "SEC 8-K",
                "title": BeautifulSoup(title, "html.parser").get_text(),
                "link": link,
                "published": published,
                "summary": BeautifulSoup(summary, "html.parser").get_text(),
            })

    return items


def make_email_body(new_items):
    if not new_items:
        return "No new executive-change alerts found today."

    lines = []
    lines.append("DAILY EXECUTIVE CHANGE ALERTS")
    lines.append("=" * 40)
    lines.append("")

    for item in new_items:
        lines.append(f"• {item['title']}")
        lines.append(f"  Source: {item['source']}")
        lines.append(f"  Link: {item['link']}")
        lines.append("")

    lines.append(f"Total Alerts: {len(new_items)}")

    return "\n".join(lines)

def send_email(subject, body):
    email_user = os.environ["EMAIL_USER"]
    email_password = os.environ["EMAIL_APP_PASSWORD"]
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = ", ".join(email_to.split(","))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_user, email_password)
        recipients = [email.strip() for email in email_to.split(",")]
        server.sendmail(email_user, recipients, msg.as_string())

def normalize_title(title):
    title = title.lower()

    # remove punctuation
    title = re.sub(r"[^\w\s]", "", title)

    # remove common filler words
    remove_words = [
        "ceo",
        "cfo",
        "chief executive officer",
        "steps down",
        "resigns",
        "appointed",
    ]

    for word in remove_words:
        title = title.replace(word, "")

    return " ".join(title.split())


def main():
    seen = load_seen()

    all_items = []
    all_items.extend(get_google_alert_items())
    all_items.extend(get_sec_8k_items())

    new_items = []
    seen_titles = set()
    for item in all_items:
        item_id = item["link"]
        
        normalized = normalize_title(item["title"])

        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)

        if item_id not in seen:
            new_items.append(item)
            seen.add(item_id)

    if new_items:
        body = make_email_body(new_items)
        send_email("Daily Executive Change Alerts", body)

    save_seen(seen)


if __name__ == "__main__":
    main()