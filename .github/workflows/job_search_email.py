import os, smtplib, requests, datetime
from email.message import EmailMessage

# Config from env
APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")
SMTP_HOST = os.getenv("EMAIL_SMTP_HOST")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_USER = os.getenv("EMAIL_SMTP_USER")
SMTP_PASS = os.getenv("EMAIL_SMTP_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")

# Search settings
country = "in"   # Adzuna country code (use 'gb', 'us', etc.); 'in' for India
what = "entry level data analyst OR junior data analyst OR data analytics intern"
results_per_page = 20

def fetch_adzuna_jobs():
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "what": what,
        "results_per_page": results_per_page,
        "content-type": "application/json"
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def is_startup(company_name):
    # Lightweight heuristic: look for short company names or keywords.
    # You can improve this by matching against a curated list of top startups.
    if not company_name:
        return False
    lname = company_name.lower()
    keywords = ["startup", "labs", "ventures", "technologies", "innovations", "solutions", "labs"]
    if any(k in lname for k in keywords):
        return True
    # fallback: treat unknowns as potential startup (optional)
    return False

def filter_jobs(raw):
    jobs = []
    for j in raw.get("results", []):
        title = j.get("title") or ""
        company = j.get("company", {}).get("display_name") or ""
        location = j.get("location", {}).get("display_name") or ""
        description = j.get("description") or ""
        redirect_url = j.get("redirect_url") or j.get("redirect_url")
        # Basic filters: entry-level keywords and startup heuristic
        low_level_keywords = ["junior", "entry", "associate", "intern", "graduate"]
        if any(k in title.lower() for k in low_level_keywords) or any(k in description.lower() for k in low_level_keywords):
            # optionally prioritize startups
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "url": redirect_url
            })
    return jobs

def compose_email(jobs):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"Daily entry-level Data Analytics job digest — {now}\n\n"
    if not jobs:
        text += "No matching jobs found.\n"
    else:
        for i, j in enumerate(jobs, 1):
            text += f"{i}. {j['title']} — {j['company']}\n   Location: {j['location']}\n   Apply: {j['url']}\n\n"
    return text

def send_email(subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

def main():
    raw = fetch_adzuna_jobs()
    jobs = filter_jobs(raw)
    # Optional: take top N and dedupe by url
    seen = set()
    dedup = []
    for j in jobs:
        if j["url"] in seen:
            continue
        seen.add(j["url"])
        dedup.append(j)
    body = compose_email(dedup[:25])  # limit to top 25
    send_email("Daily Data Analytics (Entry) Jobs — " + datetime.date.today().isoformat(), body)

if __name__ == "__main__":
    main()
