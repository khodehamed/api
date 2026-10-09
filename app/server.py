"""Persian web UI for the 0912 valuation engine."""

from __future__ import annotations

from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.valuation import load_engine

app = FastAPI(title="تخمین قیمت سیم‌کارت ۰۹۱۲")
engine = load_engine()

STATUSES = [
    ("LIKE_NEW", "در حد صفر"),
    ("BRAND_NEW_WITH_NAME", "صفر به نام"),
    ("BRAND_NEW_WITHOUT_NAME", "صفر بدون نام"),
    ("USED", "کارکرده"),
]


def _toman(value: int) -> str:
    return f"{value:,}"


def _page(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>تخمین قیمت سیم‌کارت ۰۹۱۲</title>
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; font-family: Vazirmatn, sans-serif;
    background: #0f172a; color: #e2e8f0;
    display: flex; justify-content: center; padding: 32px 16px;
  }}
  main {{ width: min(720px, 100%); }}
  h1 {{ margin: 0 0 8px; font-size: 1.5rem; color: #6ee7b7; }}
  p.lead {{ margin: 0 0 20px; color: #94a3b8; line-height: 1.7; }}
  form, .card {{
    background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    padding: 20px; margin-bottom: 16px;
  }}
  label {{ display: block; margin-bottom: 6px; color: #cbd5e1; font-size: .9rem; }}
  input, select {{
    width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid #475569;
    background: #0f172a; color: #f8fafc; font: inherit; margin-bottom: 14px;
  }}
  input {{ direction: ltr; text-align: left; letter-spacing: .08em; font-size: 1.1rem; }}
  button {{
    width: 100%; border: 0; border-radius: 12px; padding: 12px;
    background: #059669; color: white; font: inherit; font-weight: 700; cursor: pointer;
  }}
  .price {{ font-size: 1.8rem; font-weight: 700; color: #6ee7b7; }}
  .meta {{ color: #94a3b8; font-size: .85rem; line-height: 1.7; }}
  .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }}
  .badge {{
    border: 1px solid #047857; background: #064e3b; color: #a7f3d0;
    border-radius: 999px; padding: 4px 10px; font-size: .78rem;
  }}
  .badge.plain {{ border-color: #475569; background: #0f172a; color: #cbd5e1; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  th, td {{ padding: 8px 4px; border-bottom: 1px solid #334155; text-align: right; }}
  td.num, th.num {{ direction: ltr; text-align: left; }}
  a {{ color: #6ee7b7; }}
  .error {{ background: #7f1d1d; border-radius: 12px; padding: 12px; }}
</style>
</head>
<body>
<main>
  <h1>تخمین قیمت سیم‌کارت ۰۹۱۲</h1>
  <p class="lead">الگوی رند از روی قواعد بازار شناسایی می‌شود و قیمت از آگهی‌های قیمت‌دار rond.ir یاد گرفته می‌شود. خط معمولی با خط رند، و بلوک ۲۰۰ با ۲۰۱، یکی فرض نمی‌شوند.</p>
  {body}
</main>
</body>
</html>"""


def _form() -> str:
    options = "".join(f'<option value="{value}">{label}</option>' for value, label in STATUSES)
    return f"""
<form method="post" action="/estimate">
  <label for="phone">شماره سیم‌کارت</label>
  <input id="phone" name="phone" inputmode="numeric" placeholder="09121796900" required>
  <label for="status">وضعیت</label>
  <select id="status" name="status">{options}</select>
  <button type="submit">تخمین قیمت</button>
</form>
"""


def _result_html(result: dict) -> str:
    if "error" in result:
        return _page(_form() + f'<div class="error">{result["error"]}</div>')
    badges = "".join(
        f'<span class="badge{" plain" if name == "معمولی" else ""}">{name}</span>'
        for name in result["types"]
    )
    notes = " · ".join(result["notes"])
    premium = result.get("premium") or {}
    premium_html = ""
    if (
        premium
        and premium.get("pattern") != "معمولی"
        and premium.get("count", 0) >= 15
        and premium.get("premium")
        and premium.get("premium") != 1
    ):
        premium_html = (
            f'<p class="meta">در کد {premium["code"]}، میانه آگهی‌های «{premium["pattern"]}» '
            f'{_toman(premium["median"])} تومان است'
            + (
                f'؛ حدود {premium["premium"]} برابر خط معمولی همین کد.'
                if premium.get("ordinary_median")
                else "."
            )
            + f' ({premium["count"]} آگهی)</p>'
        )
    rows = "".join(
        "<tr>"
        f'<td class="num">{sample["number"]}</td>'
        f'<td>{sample["primary"]}</td>'
        f'<td class="num">{_toman(sample["price"])}</td>'
        f'<td>{sample["status"]}</td>'
        f'<td class="num">{sample["distance"]}</td>'
        "</tr>"
        for sample in result["samples"]
    )
    metrics = result.get("metrics") or {}
    ape = metrics.get("holdout_median_ape")
    ape_text = f"{ape * 100:.1f}٪" if isinstance(ape, float) else "—"
    card = f"""
<section class="card">
  <div class="meta">شماره {result["number"]} · کد {result["code"]} · بلوک {result["block3"]} · میانه {result["middle4"]}</div>
  <div class="badges">{badges}</div>
  <div class="meta">{notes}</div>
  <div style="margin-top:14px" class="meta">قیمت کارشناسی‌شده ({result["source"]})</div>
  <div class="price">{_toman(result["price"])} تومان</div>
  <div class="meta">اطمینان {result["confidence"]} · برآورد مدل به‌تنهایی {_toman(result["model_price"])} تومان</div>
  {premium_html}
</section>
<section class="card">
  <div class="meta" style="margin-bottom:8px">آگهی‌های هم‌رده که در قیمت اثر گذاشته‌اند</div>
  <table>
    <thead><tr><th class="num">شماره</th><th>رند</th><th class="num">قیمت</th><th>وضعیت</th><th class="num">فاصله</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="5">آگهی هم‌رده نزدیکی پیدا نشد.</td></tr>'}</tbody>
  </table>
  <p class="meta">خطای میانه مدل روی آگهی‌های دیده‌نشده: {ape_text}. این عدد قیمت درخواستی بازار است، نه قیمت قطعی معامله.</p>
  <p><a href="/">استعلام شماره دیگر</a></p>
</section>
"""
    return _page(_form() + card)


@app.get("/", response_class=HTMLResponse)
def home():
    return _page(_form())


@app.post("/estimate", response_class=HTMLResponse)
def estimate_form(phone: str = Form(...), status: str = Form("LIKE_NEW")):
    return _result_html(engine.estimate(phone, status))


@app.get("/api/estimate")
def estimate_api(
    phone: str = Query(...),
    status: str = Query("LIKE_NEW"),
):
    result = engine.estimate(phone, status)
    status_code = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status_code)


@app.get("/api/health")
def health():
    return {"listings": engine.metrics.get("listings"), "metrics": engine.metrics}
