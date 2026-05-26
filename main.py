import json
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

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


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen)), f, indent=2)


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

            if is_relevant(combined_text):
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

    lines = ["Executive Change Alerts", ""]

    for i, item in enumerate(new_items, start=1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"Source: {item['source']}")

        if item.get("published"):
            lines.append(f"Published: {item['published']}")

        lines.append(f"Link: {item['link']}")

        if item.get("summary"):
            lines.append(f"Summary: {item['summary'][:500]}")

        lines.append("")

    return "\n".join(lines)


def send_email(subject, body):
    email_user = os.environ["EMAIL_USER"]
    email_password = os.environ["EMAIL_APP_PASSWORD"]
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_user, email_password)
        server.send_message(msg)


def main():
    seen = load_seen()

    all_items = []
    all_items.extend(get_google_alert_items())
    all_items.extend(get_sec_8k_items())

    new_items = []
    for item in all_items:
        item_id = item["link"]

        if item_id not in seen:
            new_items.append(item)
            seen.add(item_id)

    if new_items:
        body = make_email_body(new_items)
        send_email("Daily Executive Change Alerts", body)

    save_seen(seen)


if __name__ == "__main__":
    main()