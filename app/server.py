"""Persian web UI for the 0912 valuation engine."""

from __future__ import annotations

from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.patterns import PERSIAN_DIGITS
from app.valuation import load_engine

app = FastAPI(title="قیمت سیم‌کارت ۰۹۱۲")
engine = load_engine()

STATUSES = [
    ("USED", "کارکرده"),
    ("LIKE_NEW", "در حد صفر"),
    ("BRAND_NEW_WITH_NAME", "صفر به نام"),
    ("BRAND_NEW_WITHOUT_NAME", "صفر بدون نام"),
]
STATUS_LABEL = dict(STATUSES)
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#efe8dc">
<title>۷گذر · تخمین قیمت سیم‌کارت شما</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23171412'/%3E%3Ctext x='16' y='22' text-anchor='middle' font-size='15' font-family='Georgia,serif' fill='%23f4ead7'%3E7%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    color-scheme: light;
    --ink: #171412;
    --muted: #74695c;
    --line: #e6dccb;
    --paper: #efe8dc;
    --card: #fffdf9;
    --gold: #9a7433;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    font-family: Vazirmatn, sans-serif;
    color: var(--ink);
    background:
      radial-gradient(900px 420px at 100% -10%, rgba(184, 146, 74, 0.16), transparent 55%),
      radial-gradient(700px 380px at -10% 110%, rgba(23, 20, 18, 0.05), transparent 50%),
      var(--paper);
  }
  .wrap {
    width: min(460px, calc(100% - 32px));
    padding: 36px 0 64px;
  }
  .wrap.home { margin-top: auto; margin-bottom: auto; }
  .mast { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 28px; }
  .logo {
    color: inherit; text-decoration: none; font-weight: 800; font-size: 1.35rem; letter-spacing: -0.03em;
  }
  .logo span {
    display: block; width: 26px; height: 2px; margin-top: 8px; background: var(--gold); border-radius: 2px;
  }
  .eyebrow { margin: 0; color: var(--muted); font-size: 0.82rem; font-weight: 500; }
  h1 { margin: 0 0 22px; font-size: clamp(1.45rem, 4.6vw, 1.85rem); font-weight: 800; letter-spacing: -0.04em; line-height: 1.35; }
  form, .result, .comps {
    background: var(--card);
    border: 1px solid rgba(23, 20, 18, 0.06);
    border-radius: 28px;
    box-shadow: 0 24px 50px rgba(70, 46, 16, 0.06);
  }
  form { padding: 22px 20px 20px; }
  .field {
    display: block; margin: 0 0 8px; color: var(--muted); font-size: 0.78rem; font-weight: 600;
  }
  .field.gap { margin-top: 16px; }
  input[type="text"], input:not([type]) {
    width: 100%; height: 64px; border-radius: 18px; border: 1px solid var(--line);
    background: #faf6ef; color: var(--ink); font: inherit; font-size: 1.35rem; font-weight: 600;
    letter-spacing: 0.06em; text-align: center; direction: ltr; margin-bottom: 4px;
  }
  input::placeholder { color: #c4b8a6; font-weight: 500; letter-spacing: 0.04em; }
  input:focus { outline: none; border-color: #171412; background: #fff; }
  .choices { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
  .choices label {
    position: relative; display: flex; align-items: center; justify-content: center;
    min-height: 42px; padding: 8px 10px; border-radius: 999px; border: 1px solid var(--line);
    background: #fff; color: #4e463c; font-size: 0.84rem; font-weight: 600; cursor: pointer;
    transition: background .15s ease, color .15s ease, border-color .15s ease;
  }
  .choices input { position: absolute; opacity: 0; pointer-events: none; }
  .choices label:has(input:checked) {
    background: var(--ink); color: #f6f0e6; border-color: var(--ink);
  }
  .choices label:has(input:focus-visible) { box-shadow: 0 0 0 3px rgba(154, 116, 51, 0.35); }
  button {
    width: 100%; height: 54px; border: 0; border-radius: 16px; background: var(--ink); color: #f6f0e6;
    font: inherit; font-weight: 700; font-size: 1rem; cursor: pointer;
  }
  button:hover { background: #2a241e; }
  button:active { transform: translateY(1px); }
  .error {
    margin-top: 14px; padding: 12px 14px; border-radius: 16px;
    background: #f8ece6; color: #8a332c; font-size: 0.92rem;
  }
  .result { margin-top: 18px; padding: 26px 22px 22px; }
  .number {
    margin: 0; direction: ltr; text-align: right; font-size: 1.15rem; font-weight: 700; letter-spacing: 0.04em;
  }
  .facts { margin: 8px 0 0; color: var(--muted); font-size: 0.82rem; }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
  .badge {
    border: 1px solid #eadcc4; background: #f8f1e4; color: #6d5224;
    border-radius: 999px; padding: 5px 12px; font-size: 0.8rem; font-weight: 600;
  }
  .badge.plain { background: transparent; color: #5c564c; border-color: #e3d9c8; }
  .quote { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--line); }
  .amount {
    margin: 0; font-size: clamp(1.7rem, 7vw, 2.35rem); font-weight: 800;
    letter-spacing: -0.04em; line-height: 1.15;
  }
  .kicker { margin: 0 0 6px; color: var(--muted); font-size: 0.78rem; font-weight: 600; }
  .unit { display: block; margin-top: 4px; color: var(--muted); font-size: 0.85rem; font-weight: 500; }
  .deal {
    display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
    margin-top: 16px; padding-top: 14px; border-top: 1px dashed var(--line);
  }
  .deal-label { margin: 0; color: var(--muted); font-size: 0.82rem; font-weight: 600; }
  .deal-amount { margin: 0; font-size: 1.15rem; font-weight: 800; letter-spacing: -0.03em; }
  .deal-amount span { color: var(--muted); font-size: 0.75rem; font-weight: 500; margin-inline-start: 4px; }
  .comps { margin-top: 14px; padding: 8px 22px 10px; }
  .comps h2 { margin: 14px 0 4px; font-size: 0.82rem; font-weight: 700; color: var(--muted); }
  .comp {
    display: grid; grid-template-columns: 1fr auto; gap: 2px 16px; align-items: center;
    padding: 13px 0; border-top: 1px solid #f0e7d8;
  }
  .comp:first-of-type { border-top: 0; }
  .who { direction: ltr; text-align: right; font-weight: 700; letter-spacing: 0.03em; }
  .kind { color: var(--muted); font-size: 0.78rem; margin-top: 2px; }
  .cprice { font-weight: 700; font-size: 0.92rem; letter-spacing: -0.03em; }
  @media (max-width: 420px) {
    .wrap { padding-top: 28px; }
    h1 { font-size: 1.42rem; }
    form, .result, .comps { border-radius: 22px; }
  }
</style>
</head>
<body>
<div class="wrap<!--CLASS-->">
  <div class="mast">
    <a class="logo" href="/">۷گذر<span></span></a>
    <p class="eyebrow">۰۹۱۲</p>
  </div>
  <h1>تخمین قیمت سیم‌کارت شما</h1>
  <!--BODY-->
</div>
</body>
</html>"""


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fa(value: object) -> str:
    return _esc(value).translate(FA_DIGITS)


def _toman(value: int) -> str:
    return f"{int(value):,}".replace(",", "٬").translate(FA_DIGITS)


def _phone_digits(phone: str) -> str:
    cleaned = str(phone).translate(PERSIAN_DIGITS)
    return "".join(ch for ch in cleaned if ch.isdigit())[:11]


def _phone_view(number: str) -> str:
    if len(number) == 11:
        number = f"{number[:4]} {number[4:7]} {number[7:]}"
    return number.translate(FA_DIGITS)


def _known_status(status: str) -> str:
    return status if status in STATUS_LABEL else "USED"


def _page(body: str, *, home: bool = False) -> str:
    klass = " home" if home else " answer"
    return PAGE.replace("<!--BODY-->", body).replace("<!--CLASS-->", klass)


def _form(phone: str = "", status: str = "USED") -> str:
    status = _known_status(status)
    choices = "".join(
        "<label>"
        f'<input type="radio" name="status" value="{value}"'
        f'{" checked" if value == status else ""}>'
        f"{label}</label>"
        for value, label in STATUSES
    )
    return f"""
<form method="post" action="/estimate">
  <label class="field" for="phone">شماره</label>
  <input id="phone" name="phone" type="text" inputmode="numeric" autocomplete="off" maxlength="11" placeholder="09121234567" value="{_esc(_phone_digits(phone))}" required>
  <div class="field gap">وضعیت</div>
  <div class="choices">{choices}</div>
  <button type="submit">نمایش قیمت</button>
</form>
"""


def _result_html(result: dict, phone: str, status: str) -> str:
    form = _form(phone or result.get("number", ""), status)
    if "error" in result:
        return _page(form + f'<p class="error">{_esc(result["error"])}</p>')
    badges = "".join(
        f'<span class="badge{" plain" if name == "معمولی" else ""}">{_esc(name)}</span>'
        for name in result["types"]
    )
    status_label = STATUS_LABEL.get(result.get("status") or status, STATUS_LABEL["USED"])
    facts = " · ".join(
        [
            f"کد {_fa(result['code'])}",
            f"بلوک {_fa(result['block3'])}",
            f"میانه {_fa(result['middle4'])}",
            status_label,
        ]
    )
    comps = ""
    if result["samples"]:
        rows = "".join(
            "<div class='comp'>"
            "<div>"
            f"<div class='who'>{_phone_view(sample['number'])}</div>"
            f"<div class='kind'>{_esc(sample['primary'])} · {_esc(STATUS_LABEL.get(sample['status'], sample['status']))}</div>"
            "</div>"
            f"<div class='cprice'>{_toman(sample['price'])}</div>"
            "</div>"
            for sample in result["samples"]
        )
        comps = f"<section class='comps'><h2>آگهی‌های نزدیک</h2>{rows}</section>"
    card = f"""
<section class="result">
  <p class="number">{_phone_view(result["number"])}</p>
  <p class="facts">{facts}</p>
  <div class="badges">{badges}</div>
  <div class="quote">
    <p class="kicker">تخمین</p>
    <p class="amount">{_toman(result["price"])}</p>
    <span class="unit">تومان</span>
    <div class="deal">
      <p class="deal-label">قیمت معامله</p>
      <p class="deal-amount">{_toman(result["deal_price"])} <span>تومان</span></p>
    </div>
  </div>
</section>
{comps}
"""
    return _page(form + card)


@app.get("/", response_class=HTMLResponse)
def home():
    return _page(_form(), home=True)


@app.post("/estimate", response_class=HTMLResponse)
def estimate_form(phone: str = Form(...), status: str = Form("USED")):
    return _result_html(engine.estimate(phone, status), phone, status)


@app.get("/api/estimate")
def estimate_api(
    phone: str = Query(...),
    status: str = Query("USED"),
):
    result = engine.estimate(phone, status)
    status_code = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status_code)


@app.get("/api/health")
def health():
    return {
        "listings": engine.metrics.get("listings"),
        "refreshed_at": engine.metrics.get("refreshed_at"),
        "metrics": engine.metrics,
    }
