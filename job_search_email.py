import os
import smtplib
import requests
import datetime
import json
import re
import pandas as pd
from fpdf import FPDF
import google.generativeai as genai
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# --- CONFIGURATION ---
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SMTP_HOST = os.getenv("EMAIL_SMTP_HOST")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_USER = os.getenv("EMAIL_SMTP_USER")
SMTP_PASS = os.getenv("EMAIL_SMTP_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")

# --- USER SETTINGS ---
LOCATIONS = ["chennai", "bangalore", "bengaluru", "hyderabad", "remote", "pune", "work from home"]
BLACKLIST = ["training", "placement agency", "paid", "academy", "consultancy", "job agency"]
MY_SKILLS = ["python", "django", "flask", "sql", "react", "pandas", "numpy", "aws", "machine learning"]

COUNTRY = "in"
WHAT = "python"

# --- AI SETUP ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def fetch_jobs():
    print(f"DEBUG: Fetching jobs...")
    url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID, 
        "app_key": ADZUNA_APP_KEY, 
        "what": WHAT, 
        "results_per_page": 50,
        "content-type": "application/json"
    }
    resp = requests.get(url, params=params)
    return resp.json().get("results", [])

def scan_skills(text):
    """Finds which of your skills are mentioned in the job description."""
    found = [skill for skill in MY_SKILLS if skill in text.lower()]
    return ", ".join(found).title() if found else "General"

def extract_salary(text):
    """Fallback Regex for salary if AI fails."""
    # Matches: 12 LPA, 12-15 Lakhs, 50000/mo
    lpa = re.search(r'(\d+[\.]?\d*)\s?-?\s?(\d+[\.]?\d*)?\s?(LPA|Lakhs)', text, re.IGNORECASE)
    if lpa: return lpa.group(0)
    
    stipend = re.search(r'₹?\s?(\d{2,6})\s?/?(mo|month)', text, re.IGNORECASE)
    if stipend: return stipend.group(0)
    
    return "Not Disclosed"

def analyze_job(job):
    """Uses Gemini AI (or logic) to rate job and find salary."""
    text = (job.get('title') + " " + job.get('description')).lower()
    
    # 1. Base Logic
    skills = scan_skills(text)
    salary = extract_salary(text)
    is_intern = any(k in text for k in ["intern", "trainee", "stipend"])
    rating = "N/A"

    # 2. AI Enhancement (Only if Key exists)
    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"""
            Analyze this job for a Python Fresher.
            Title: {job.get('title')}
            Desc: {job.get('description')}[:1000] 
            
            Return JSON:
            {{ "rating": "1-10 (Int)", "salary": "Estimate (Str)", "reason": "Short reason" }}
            """
            resp = model.generate_content(prompt)
            data = json.loads(resp.text.replace("```json", "").replace("```", ""))
            
            rating = data.get("rating", "N/A")
            if salary == "Not Disclosed": 
                salary = data.get("salary", "Unknown")
        except:
            pass # Fail silently to regex logic

    return rating, salary, skills, is_intern

def process_jobs(raw):
    processed = {"Internships": [], "Jobs": []}
    stats = {"Remote": 0, "HighRated": 0, "Total": 0}
    
    for j in raw:
        loc = j.get('location', {}).get('display_name', '').lower()
        company = j.get('company', {}).get('display_name', '')
        
        # --- FILTERS ---
        if not any(l in loc for l in LOCATIONS): continue
        if any(b in company.lower() for b in BLACKLIST): continue
        
        # --- ANALYSIS ---
        rating, salary, skills, is_intern = analyze_job(j)
        
        # Update Stats
        stats["Total"] += 1
        if "remote" in loc: stats["Remote"] += 1
        if isinstance(rating, int) and rating >= 8: stats["HighRated"] += 1

        entry = {
            "Title": j.get('title'),
            "Company": company,
            "Location": j.get('location', {}).get('display_name'),
            "Salary": salary,
            "Rating": rating,
            "Skills": skills,
            "URL": j.get('redirect_url')
        }
        
        if is_intern:
            processed["Internships"].append(entry)
        else:
            processed["Jobs"].append(entry)
            
    # Sort: Highest rated first
    processed["Internships"].sort(key=lambda x: str(x['Rating']), reverse=True)
    processed["Jobs"].sort(key=lambda x: str(x['Rating']), reverse=True)
    
    return processed, stats

def create_excel(data):
    # Combine all data for Excel
    all_jobs = data["Internships"] + data["Jobs"]
    if not all_jobs: return None
    
    df = pd.DataFrame(all_jobs)
    filename = f"Jobs_{datetime.date.today()}.xlsx"
    df.to_excel(filename, index=False)
    return filename

def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Daily Job Intelligence Report", ln=True, align='C')
    pdf.ln(10)
    
    for category, jobs in data.items():
        if not jobs: continue
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"{category} ({len(jobs)})", ln=True, fill=True)
        
        pdf.set_font("Arial", size=10)
        for job in jobs:
            title = job['Title'].encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 8, f"[{job['Rating']}/10] {title}", ln=True)
            pdf.set_font("Arial", 'I', 9)
            pdf.cell(0, 5, f"   {job['Company']} | Skills: {job['Skills']}", ln=True)
            pdf.set_font("Arial", size=9)
            pdf.cell(0, 5, f"   Salary: {job['Salary']} | Link: {job['URL']}", ln=True)
            pdf.ln(3)
            
    filename = f"Jobs_{datetime.date.today()}.pdf"
    pdf.output(filename)
    return filename

def generate_html_email(data, stats):
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4; padding: 20px; }}
            .container {{ background-color: white; border-radius: 8px; overflow: hidden; max-width: 600px; margin: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background-color: #2c3e50; color: white; padding: 25px; text-align: center; }}
            .stats-bar {{ display: flex; justify-content: space-around; background: #34495e; color: white; padding: 10px; font-size: 14px; }}
            .section-title {{ color: #2c3e50; border-bottom: 2px solid #3498db; margin: 20px; padding-bottom: 5px; font-size: 18px; }}
            .job-card {{ padding: 15px; margin: 15px; border: 1px solid #e0e0e0; border-radius: 6px; background: #fff; border-left: 5px solid #3498db; }}
            .job-title {{ font-size: 16px; font-weight: bold; color: #2980b9; }}
            .skills {{ background: #eef2f3; color: #555; padding: 3px 8px; border-radius: 4px; font-size: 12px; display: inline-block; margin-top: 5px; }}
            .salary {{ color: #27ae60; font-weight: bold; font-size: 14px; margin-top: 5px; }}
            .apply-btn {{ display: block; width: 100%; background-color: #3498db; color: white; text-align: center; padding: 10px 0; margin-top: 10px; text-decoration: none; border-radius: 4px; font-weight: bold; }}
            .rating-badge {{ float: right; background: #f1c40f; color: #333; padding: 2px 6px; border-radius: 10px; font-size: 12px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🚀 Daily Career Intel</h2>
            </div>
            <div class="stats-bar">
                <span>Total: {stats['Total']}</span>
                <span>Remote: {stats['Remote']}</span>
                <span>Top Rated: {stats['HighRated']}</span>
            </div>
    """
    
    for category, jobs in data.items():
        if not jobs: continue
        html += f"<h3 class='section-title'>{category}</h3>"
        
        for job in jobs[:7]: # Limit email length
            html += f"""
            <div class="job-card">
                <span class="rating-badge">★ {job['Rating']}</span>
                <div class="job-title">{job['Title']}</div>
                <div style="color: #7f8c8d; font-size: 13px;">{job['Company']} • {job['Location']}</div>
                <div class="skills">🛠 {job['Skills']}</div>
                <div class="salary">💰 {job['Salary']}</div>
                <a href="{job['URL']}" class="apply-btn">Apply Now</a>
            </div>
            """
            
    html += """<div style="padding: 20px; text-align: center; color: #888; font-size: 12px;">
                Excel and PDF reports attached. <br> Automated by GitHub Actions.
               </div></div></body></html>"""
    return html

def send_email(html_body, files):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg['Subject'] = f"📊 Job Report: {datetime.date.today()} (Files Attached)"

    msg.attach(MIMEText(html_body, 'html'))

    for f in files:
        if f and os.path.exists(f):
            with open(f, "rb") as content:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(content.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f"attachment; filename={f}")
                msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

if __name__ == "__main__":
    try:
        raw = fetch_jobs()
        data, stats = process_jobs(raw)
        
        if stats["Total"] > 0:
            excel_file = create_excel(data)
            pdf_file = create_pdf(data)
            html = generate_html_email(data, stats)
            
            # Send Email with BOTH files
            send_email(html, [excel_file, pdf_file])
            print(f"Success! Email sent with Excel & PDF. Stats: {stats}")
        else:
            print("No jobs found today matching filters.")
            
    except Exception as e:
        print(f"Error: {e}")
