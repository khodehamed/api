from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid as uuid_tool
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import requests
from flask import Flask, jsonify, render_template_string, request

# Disable warnings for panels that still use self-signed certificates.
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# اگر می‌خواهید اطلاعات ورود را مستقیم داخل همین فایل بگذارید، این بخش را پر کنید.
# اگر INLINE_PANEL_TOKEN پر باشد، برنامه از توکن استفاده می‌کند و یوزر/پس لازم نیست.
INLINE_PANEL_USERNAME = "hamex"
INLINE_PANEL_PASSWORD = ""  # مثال: "your-panel-password"
INLINE_PANEL_TOKEN = ""  # مثال: "your-3x-ui-api-token"
INLINE_CHANGE_SECTION_PASSWORD = "7gozar"


@dataclass(frozen=True)
class PanelConfig:
    url: str
    domain: str
    username: str | None = None
    password: str | None = None
    token: str | None = None


DEFAULT_PANEL_ENDPOINTS = {
    "linkw.gozar8.ir": {"url": "https://5.57.38.18:2096/hamex", "domain": "linkw.gozar8.ir"},
    "link.gozar8.ir": {"url": "https://5.57.38.14:2096/hamex", "domain": "link.gozar8.ir"},
    "linkn.gozar8.ir": {"url": "https://81.12.32.89:2096/hamex", "domain": "linkn.gozar8.ir"},
    "linkm.gozar8.ir": {"url": "https://178.239.145.42:2096/hamex", "domain": "linkm.gozar8.ir"},
    "linkh.gozar8.ir": {"url": "https://178.239.145.43:2096/hamex", "domain": "linkh.gozar8.ir"},
    "rsk.gozar8.ir": {"url": "https://5.57.38.15:2096/hamex", "domain": "rsk.gozar8.ir"},
    "linksh.gozar8.ir": {"url": "http://178.239.145.39:2096/hamex", "domain": "linksh.gozar8.ir"},
    "links.gozar8.ir": {"url": "https://178.239.145.45:2096/hamex", "domain": "links.gozar8.ir"},
    "linkt.gozar8.ir": {"url": "https://178.239.145.41:2096/hamex", "domain": "linkt.gozar8.ir"},
    "login.gozqr9.ir": {"url": "https://5.57.38.20:2096/hamex", "domain": "login.gozqr9.ir"},
}


def _panel_env_key(domain: str, suffix: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", domain).strip("_").upper()
    return f"XUI_{normalized}_{suffix}"


def load_panels() -> dict[str, PanelConfig]:
    raw_json = os.getenv("PANELS_JSON", "").strip()
    if raw_json:
        try:
            loaded = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("PANELS_JSON is not valid JSON") from exc
        if isinstance(loaded, list):
            entries = {item["domain"]: item for item in loaded}
        elif isinstance(loaded, dict):
            entries = loaded
        else:
            raise RuntimeError("PANELS_JSON must be an object or an array")
    else:
        entries = DEFAULT_PANEL_ENDPOINTS

    default_username = os.getenv("XUI_PANEL_USERNAME", INLINE_PANEL_USERNAME).strip() or None
    default_password = os.getenv("XUI_PANEL_PASSWORD", INLINE_PANEL_PASSWORD).strip() or None
    default_token = os.getenv("XUI_PANEL_TOKEN", INLINE_PANEL_TOKEN).strip() or None

    panels: dict[str, PanelConfig] = {}
    for name, item in entries.items():
        domain = str(item.get("domain") or name).lower().strip()
        username = (
            os.getenv(_panel_env_key(domain, "USERNAME"), "").strip()
            or item.get("username")
            or default_username
        )
        password = (
            os.getenv(_panel_env_key(domain, "PASSWORD"), "").strip()
            or item.get("password")
            or default_password
        )
        token = (
            os.getenv(_panel_env_key(domain, "TOKEN"), "").strip()
            or item.get("token")
            or default_token
        )
        panels[domain] = PanelConfig(
            url=str(item["url"]).rstrip("/"),
            domain=domain,
            username=username,
            password=password,
            token=token,
        )
    return panels


PANELS = load_panels()
CHANGE_SECTION_PASSWORD = os.getenv("CHANGE_SECTION_PASSWORD", INLINE_CHANGE_SECTION_PASSWORD)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seven Hub ..</title>
    <script src="{{ url_for('static', filename='jquery-3.6.0.min.js') }}"></script>
    <style>
        :root { --accent: #00d4ff; --accent-alt: #00ffaa; --toggle-color: #ffb700; --danger: #ff4747; --warning: #ffaa00; --bg: #020205; --success: #00ffaa; }
        body, html { margin: 0; padding: 0; width: 100%; height: 100%; background: var(--bg); font-family: 'Tahoma', sans-serif; color: white; overflow-x: hidden; }
        
        canvas { position: fixed; top: 0; left: 0; z-index: 1; pointer-events: none; }
        .container { min-height: 100vh; display: flex; justify-content: center; align-items: center; position: relative; z-index: 10; padding: 20px; box-sizing: border-box; }
        .card {
            background: rgba(10, 10, 15, 0.95); backdrop-filter: blur(25px);
            border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 35px;
            padding: 35px; width: 100%; max-width: 460px;
            box-shadow: 0 50px 100px rgba(0, 0, 0, 0.9); text-align: center;
        }
        h2 { font-weight: 200; letter-spacing: 5px; font-size: 18px; margin-bottom: 25px; color: #fff; }
        .tabs { display: flex; justify-content: center; gap: 5px; margin-bottom: 25px; background: rgba(255,255,255,0.03); padding: 5px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.05); }
        .tab-btn { flex: 1; padding: 10px 5px; background: transparent; color: #888; border: none; border-radius: 14px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.3s; white-space: nowrap; }
        .tab-btn.active { background: rgba(255,255,255,0.08); color: #fff; }
        .tab-btn:hover:not(.active) { color: #fff; background: rgba(255,255,255,0.03); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        textarea {
            width: 100%; background: rgba(0,0,0,0.6); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 18px; padding: 15px; color: var(--accent); resize: none; outline: none;
            font-family: monospace; font-size: 12px; direction: ltr; box-sizing: border-box;
        }
        .tab-content[data-tab="changer"] textarea { color: var(--accent-alt); }
        .tab-content[data-tab="toggle"] textarea { color: var(--toggle-color); }
        .btn-group { display: flex; flex-direction: column; gap: 10px; margin-top: 25px; }
        
        .btn-check { 
            padding: 16px; border-radius: 18px; border: none; background: #fff; 
            color: #000; font-weight: 800; cursor: pointer; transition: 0.3s;
        }
        .btn-check:hover { background: var(--accent); transform: translateY(-2px); }
        .tab-content[data-tab="changer"] .btn-check:hover { background: var(--accent-alt); }
        .tab-content[data-tab="toggle"] .btn-check:hover { background: var(--toggle-color); }
        .btn-clear { 
            padding: 14px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.2); 
            background: transparent; color: #bbb; cursor: pointer; transition: 0.3s;
        }
        .btn-clear:hover { background: var(--danger); color: #fff; border-color: var(--danger); }
        .loader-wrap { display: none; margin: 25px 0; justify-content: center; }
        .modern-loader {
            width: 30px; height: 30px;
            border: 3px solid rgba(255, 255, 255, 0.05);
            border-top: 3px solid var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        .tab-content[data-tab="changer"] .modern-loader { border-top-color: var(--accent-alt); }
        .tab-content[data-tab="toggle"] .modern-loader { border-top-color: var(--toggle-color); }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .result-box { margin-top: 30px; display: none; text-align: right; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 20px; }
        .info-card { background: rgba(255, 255, 255, 0.02); padding: 25px; border-radius: 25px; border: 1px solid rgba(255,255,255,0.03); }
        
        .label { color: #666; font-size: 11px; display: block; margin-bottom: 5px; font-weight: bold; }
        .val { color: #fff; font-size: 14px; font-weight: 600; margin-bottom: 15px; display: block; }
        
        .status-row { display: flex; justify-content: space-between; margin-bottom: 15px; background: rgba(255,255,255,0.01); padding: 10px 15px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.02); }
        .status-row .label { margin: 0; display: flex; align-items: center; }
        .badge { font-size: 12px; font-weight: bold; padding: 2px 10px; border-radius: 8px; }
        .badge.active { background: rgba(0, 255, 170, 0.1); color: var(--success); }
        .badge.disabled { background: rgba(255, 71, 71, 0.1); color: var(--danger); }
        .badge.online { background: rgba(0, 212, 255, 0.1); color: var(--accent); }
        .badge.offline { background: rgba(255, 255, 255, 0.05); color: #888; }
        #finishMsg { 
            display: none; background: rgba(255, 71, 71, 0.1); color: var(--danger); 
            padding: 12px; border-radius: 15px; font-size: 13px; font-weight: bold; 
            text-align: center; margin-bottom: 15px; border: 1px solid rgba(255, 71, 71, 0.2);
        }
        .progress-box { height: 6px; background: rgba(255,255,255,0.05); border-radius: 10px; margin: 15px 0; overflow: hidden; }
        .progress-fill { height: 100%; width: 0%; transition: 2s ease-out; background: var(--accent); box-shadow: 0 0 10px var(--accent); }
        .warning-box {
            background: rgba(255, 71, 71, 0.06);
            border: 1px dashed rgba(255, 71, 71, 0.4);
            border-radius: 20px;
            padding: 16px;
            margin-bottom: 20px;
            text-align: justify;
            line-height: 1.8;
            box-shadow: 0 0 15px rgba(255, 71, 71, 0.05);
            animation: pulse-border 2s infinite alternate;
        }
        .warning-box strong { color: #ff5555; display: flex; align-items: center; gap: 5px; font-size: 14px; margin-bottom: 6px; }
        .warning-box p { margin: 0; color: #e0e0e0; font-size: 12px; font-weight: 300; }
        @keyframes pulse-border {
            0% { border-color: rgba(255, 71, 71, 0.3); box-shadow: 0 0 10px rgba(255, 71, 71, 0.02); }
            100% { border-color: rgba(255, 71, 71, 0.7); box-shadow: 0 0 20px rgba(255, 71, 71, 0.15); }
        }
        .success-tag { color: var(--accent-alt); font-weight: bold; margin-bottom: 15px; font-size: 14px; text-align: center; }
        .status-tag { font-weight: bold; padding: 10px; border-radius: 14px; text-align: center; font-size: 14px; margin-bottom: 15px; }
        .status-tag.active-status { background: rgba(0, 255, 170, 0.1); color: var(--accent-alt); border: 1px solid rgba(0, 255, 170, 0.2); }
        .status-tag.disabled-status { background: rgba(255, 71, 71, 0.1); color: var(--danger); border: 1px solid rgba(255, 71, 71, 0.2); }
        
        .qr-box { background: white; padding: 12px; border-radius: 20px; display: inline-block; margin: 15px auto 0 auto; }
        .qr-box img { width: 180px; height: 180px; display: block; }
        .copy-btn { background: rgba(255,255,255,0.05); color: #fff; border: 1px solid rgba(255, 255, 255, 0.1); padding: 10px 20px; border-radius: 12px; font-size: 12px; margin-top: 10px; cursor: pointer; transition: 0.3s; width: 100%; }
        .copy-btn:hover { background: #fff; color: #000; }
        .error-msg { color: var(--danger); font-size: 12px; margin-top: 15px; text-align: center; }
    </style>
</head>
<body>
    <canvas id="starfield"></canvas>
    
    <div class="container">
        <div class="card">
            <h2>Seven <span style="font-weight:900; color:var(--accent)" id="brandTitle">HUB</span></h2>
            
            <div class="tabs">
                <button class="tab-btn active" onclick="switchTab('check')">بررسی وضعیت</button>
                <button class="tab-btn" onclick="switchTab('changer')">تغییر پورت (UUID/Pass)</button>
                <button class="tab-btn" onclick="switchTab('toggle')">قطع/وصلی موقت</button>
            </div>
            <div class="tab-content active" data-tab="check">
                <textarea id="vlessLink" rows="3" placeholder="....لینک VLESS یا Shadowsocks را جهت بررسی وضعیت وارد کنید"></textarea>
                <div class="btn-group">
                    <button class="btn-check" onclick="checkAccount()">بررسی وضعیت</button>
                    <button class="btn-clear" onclick="clearCheckForm()">پاکسازی فرم</button>
                </div>
                <div class="loader-wrap" id="checkLoader"><div class="modern-loader"></div></div>
                
                <div class="result-box" id="checkResult">
                    <div class="info-card">
                        <div id="finishMsg">حجم اشتراک شما به پایان رسیده است ❌</div>
                        
                        <div class="status-row">
                            <span class="label">وضعیت اتصال:</span>
                            <span id="resIsEnable" class="badge">-</span>
                        </div>
                        <div class="status-row">
                            <span class="label">وضعیت حضور:</span>
                            <span id="resIsOnline" class="badge">-</span>
                        </div>
                        <span class="label">شناسه کاربر / ایمیل</span>
                        <span id="resEmail" class="val" style="direction:ltr;">-</span>
                        <span class="label">ترافیک مصرف شده</span>
                        <span id="resUsage" class="val" style="direction:ltr;">-</span>
                        <div class="progress-box"><div id="resBar" class="progress-fill"></div></div>
                        <span class="label">زمان باقی‌مانده</span>
                        <span id="resExpiry" class="val">-</span>
                    </div>
                </div>
                <div class="error-msg" id="checkError"></div>
            </div>
            <div class="tab-content" data-tab="changer">
                <div class="warning-box">
                    <strong>⚠️ توجه بسیار مهم:</strong>
                    <p>در صورت تغییر دادن پورت یا رمز، <b>لینک اتصال قدیمی شما فوراً و برای همیشه از دسترس خارج خواهد شد</b>. لینک جدید با همان مشخصات قبلی صادر می‌شود.</p>
                </div>
                <textarea id="oldLink" rows="3" placeholder="....لینک قدیمی کلاینت را جهت تغییر پورت/رمز وارد کنید"></textarea>
                <div class="btn-group">
                    <button class="btn-check" id="changeBtn" onclick="changeUuid()">تغییر پورت و صدور لینک جدید</button>
                    <button class="btn-clear" onclick="clearChangerForm()">پاکسازی فرم</button>
                </div>
                <div class="loader-wrap" id="changerLoader"><div class="modern-loader"></div></div>
                
                <div class="result-box" id="changerResult">
                    <div class="info-card">
                        <div class="success-tag">✓ کانفیگ با موفقیت به روز رسانی شد</div>
                        <span class="label">ایمیل کلاینت</span>
                        <span id="clientEmail" class="val" style="direction:ltr; text-align:right;">-</span>
                        <span class="label">لینک اتصال جدید</span>
                        <textarea id="newLink" rows="3" readonly style="color: #fff; background: rgba(255,255,255,0.02); margin-bottom:10px;"></textarea>
                        <button class="copy-btn" onclick="copyLink()">کپی کردن لینک جدید</button>
                        <div style="text-align: center;">
                            <div class="qr-box">
                                <img id="qrImage" src="" alt="QR Code">
                            </div>
                        </div>
                    </div>
                </div>
                <div class="error-msg" id="changerError"></div>
            </div>
            <div class="tab-content" data-tab="toggle">
                <textarea id="toggleLink" rows="3" placeholder="....لینک کلاینت را جهت قطع یا وصل کردن وارد کنید"></textarea>
                <div class="btn-group">
                    <button class="btn-check" id="toggleBtn" onclick="toggleStatus()">تغییر وضعیت اتصال (روشن/خاموش)</button>
                    <button class="btn-clear" onclick="clearToggleForm()">پاکسازی فرم</button>
                </div>
                <div class="loader-wrap" id="toggleLoader"><div class="modern-loader"></div></div>
                
                <div class="result-box" id="toggleResult">
                    <div class="info-card">
                        <div id="statusLabel" class="status-tag">-</div>
                        <span class="label">ایمیل کاربر</span>
                        <span id="toggleEmail" class="val" style="direction:ltr; text-align:right;">-</span>
                    </div>
                </div>
                <div class="error-msg" id="toggleError"></div>
            </div>
        </div>
    </div>
    <script>
        const canvas = document.getElementById('starfield');
        const ctx = canvas.getContext('2d');
        let stars = [];
        
        function initStars() {
            canvas.width = window.innerWidth; canvas.height = window.innerHeight;
            stars = [];
            for (let i = 0; i < 800; i++) {
                stars.push({ 
                    x: Math.random() * canvas.width, 
                    y: Math.random() * canvas.height, 
                    size: Math.random() * 1.5, 
                    speed: Math.random() * 0.3 + 0.1, 
                    o: Math.random() 
                });
            }
        }
        
        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height); 
            ctx.fillStyle = "#fff";
            stars.forEach(s => {
                ctx.globalAlpha = s.o; 
                ctx.beginPath(); 
                ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2); 
                ctx.fill();
                s.y -= s.speed; 
                if (s.y < 0) s.y = canvas.height;
            });
            requestAnimationFrame(draw);
        }
        
        initStars(); draw();
        window.addEventListener('resize', initStars);
        function switchTab(tabName) {
            $('.tab-btn').removeClass('active');
            $('.tab-content').removeClass('active');
            
            $(`.tab-btn[onclick="switchTab('${tabName}')"]`).addClass('active');
            $(`.tab-content[data-tab="${tabName}"]`).addClass('active');
            
            if(tabName === 'check') {
                $('#brandTitle').text('CHECK').css('color', 'var(--accent)');
            } else if(tabName === 'changer') {
                $('#brandTitle').text('CHANGER').css('color', 'var(--accent-alt)');
            } else {
                $('#brandTitle').text('SWITCH').css('color', 'var(--toggle-color)');
            }
        }
        function clearCheckForm() { $('#vlessLink').val(''); $('#checkResult').hide(); $('#checkError').text(''); $('#checkLoader').hide(); }
        function clearChangerForm() { $('#oldLink').val(''); $('#changerResult').hide(); $('#changerError').text(''); $('#changerLoader').hide(); }
        function clearToggleForm() { $('#toggleLink').val(''); $('#toggleResult').hide(); $('#toggleError').text(''); $('#toggleLoader').hide(); }
        function checkAccount() {
            const link = $('#vlessLink').val().trim();
            if(!link) return;
            $('#checkResult').hide(); $('#checkError').text(''); $('#checkLoader').css('display', 'flex');
            
            $.post('/api/check', { link: link }, function(data) {
                $('#checkLoader').hide();
                if(data.success) {
                    $('#resEmail').text(data.email);
                    $('#resUsage').text(data.used + " / " + data.total);
                    $('#resExpiry').text(data.expiry);
                    
                    if(data.is_enable) {
                        $('#resIsEnable').text('فعال (روشن) ✔').removeClass('disabled').addClass('active');
                    } else {
                        let statusText = data.is_expired ? 'غیرفعال (منقضی شده) ✖' : 'غیرفعال (خاموش) ✖';
                        $('#resIsEnable').text(statusText).removeClass('active').addClass('disabled');
                    }
                    
                    if(data.is_online) {
                        $('#resIsOnline').text('آنلاین ●').removeClass('offline').addClass('online');
                    } else {
                        $('#resIsOnline').text('آفلاین ○').removeClass('online').addClass('offline');
                    }
                    const isFinished = data.percent >= 100;
                    if(isFinished) {
                        $('#finishMsg').show();
                        $('#resBar').css({'background': 'var(--danger)', 'box-shadow': '0 0 10px var(--danger)'});
                    } else {
                        $('#finishMsg').hide();
                        $('#resBar').css({'background': 'var(--accent)', 'box-shadow': '0 0 10px var(--accent)'});
                    }
                    $('#checkResult').fadeIn(400);
                    setTimeout(() => $('#resBar').css('width', Math.min(data.percent, 100) + '%'), 100);
                } else { 
                    $('#checkError').text(data.message); 
                }
            }).fail(() => { $('#checkLoader').hide(); $('#checkError').text('خطا در ارتباط با سرور!'); });
        }
        function changeUuid(password = null) {
            const link = $('#oldLink').val().trim();
            if(!link) return;
            $('#changerResult').hide(); $('#changerError').text(''); $('#changerLoader').css('display', 'flex'); $('#changeBtn').prop('disabled', true);
            
            let postData = { link: link };
            if (password) {
                postData.password = password;
            }
            
            $.post('/api/change', postData, function(data) {
                if (data.needs_password) {
                    $('#changerLoader').hide(); $('#changeBtn').prop('disabled', false);
                    let promptMsg = data.message;
                    let userPass = prompt(promptMsg);
                    if (userPass !== null) {
                        changeUuid(userPass);
                    }
                    return;
                }
                
                $('#changerLoader').hide(); $('#changeBtn').prop('disabled', false);
                if(data.success) {
                    $('#clientEmail').text(data.email);
                    $('#newLink').val(data.new_link);
                    $('#qrImage').attr('src', 'data:image/png;base64,' + data.qr);
                    $('#changerResult').fadeIn(400);
                } else {
                    $('#changerError').text(data.message);
                }
            }, 'json').fail(() => { 
                $('#changerLoader').hide(); $('#changeBtn').prop('disabled', false); 
                $('#changerError').text('خطا در ارتباط با سرور پایتون!'); 
            });
        }
        function toggleStatus() {
            const link = $('#toggleLink').val().trim();
            if(!link) return;
            $('#toggleResult').hide(); $('#toggleError').text(''); $('#toggleLoader').css('display', 'flex'); $('#toggleBtn').prop('disabled', true);
            
            $.post('/api/toggle', { link: link }, function(data) {
                $('#toggleLoader').hide(); $('#toggleBtn').prop('disabled', false);
                if(data.success) {
                    $('#toggleEmail').text(data.email);
                    if(data.current_status) {
                        $('#statusLabel').text('● وضعیت فعلی: متصل (روشن)').removeClass('disabled-status').addClass('active-status');
                    } else {
                        $('#statusLabel').text('○ وضعیت فعلی: قطع شده (خاموش)').removeClass('disabled-status').addClass('active-status');
                    }
                    $('#toggleResult').fadeIn(400);
                } else {
                    $('#toggleError').text(data.message);
                }
            }, 'json').fail(() => {
                $('#toggleLoader').hide(); $('#toggleBtn').prop('disabled', false);
                $('#toggleError').text('خطا در ارتباط با سرور پایتون!');
            });
        }
        function copyLink() {
            const copyText = document.getElementById("newLink");
            copyText.select();
            copyText.setSelectionRange(0, 99999);
            document.execCommand("copy");
            alert("لینک جدید با موفقیت کپی شد.");
        }
    </script>
</body>
</html>
"""


def format_bytes(size: Any) -> str:
    try:
        size_float = float(size or 0)
    except (TypeError, ValueError):
        size_float = 0
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_float < 1024:
            return f"{size_float:.2f} {unit}"
        size_float /= 1024
    return f"{size_float:.2f} PB"


def _b64decode_urlsafe(value: str) -> bytes:
    value = value.strip()
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("utf-8"))


def _b64encode_urlsafe(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


def parse_config_link(link: str) -> tuple[str | None, str | None, str | None]:
    link = link.strip()
    if link.startswith("vless://"):
        match_uuid = re.search(r"vless://([^@]+)@", link, re.IGNORECASE)
        match_domain = re.search(r"@([^/\?:#]+)", link)
        if match_uuid and match_domain:
            return "vless", unquote(match_uuid.group(1)), match_domain.group(1).lower().strip()

    if link.startswith("ss://"):
        parsed = parse_ss_link(link)
        if parsed:
            return "ss", ss_panel_password_from_link_password(parsed["method"], parsed["password"]), parsed["domain"]

    return None, None, None


def parse_ss_link(link: str) -> dict[str, str] | None:
    body, _, fragment = link[5:].partition("#")
    body = body.split("?", 1)[0]
    try:
        if "@" in body:
            user_info, host_part = body.rsplit("@", 1)
            host = urlsplit(f"//{host_part}").hostname or host_part.split(":", 1)[0]
            decoded = ""
            try:
                decoded = _b64decode_urlsafe(user_info).decode("utf-8", errors="strict")
            except Exception:
                pass
            if ":" not in decoded:
                decoded = unquote(user_info)
            if ":" not in decoded:
                return None
            method, password = decoded.split(":", 1)
            return {
                "method": method,
                "password": password,
                "domain": host.lower().strip(),
                "style": "userinfo",
                "remark": unquote(fragment).strip(),
            }

        decoded = _b64decode_urlsafe(body).decode("utf-8", errors="strict")
        if "@" not in decoded or ":" not in decoded.split("@", 1)[0]:
            return None
        user_info, host_part = decoded.rsplit("@", 1)
        method, password = user_info.split(":", 1)
        host = urlsplit(f"//{host_part}").hostname or host_part.split(":", 1)[0]
        return {
            "method": method,
            "password": password,
            "domain": host.lower().strip(),
            "style": "full",
            "remark": unquote(fragment).strip(),
        }
    except Exception:
        return None


def ss_panel_password_from_link_password(method: str, password: str) -> str:
    if method.startswith("2022-blake3-") and ":" in password:
        return password.rsplit(":", 1)[1]
    return password


def ss_link_password_with_new_client_key(method: str, old_password: str, new_client_key: str) -> str:
    if method.startswith("2022-blake3-") and ":" in old_password:
        server_key = old_password.rsplit(":", 1)[0]
        return f"{server_key}:{new_client_key}"
    return new_client_key


def ss_match_values(client_key: str, link: str | None = None) -> set[str]:
    values = {client_key, unquote(client_key)}
    if ":" in client_key:
        values.add(client_key.rsplit(":", 1)[1])

    if link:
        parsed = parse_ss_link(link)
        if parsed:
            password = parsed.get("password", "")
            method = parsed.get("method", "")
            remark = parsed.get("remark", "")
            values.add(password)
            values.add(ss_panel_password_from_link_password(method, password))
            if ":" in password:
                values.add(password.rsplit(":", 1)[1])
            if remark:
                values.add(remark)

    return {value for value in values if value}


def ss_client_matches(client: dict[str, Any], client_key: str, link: str | None = None) -> bool:
    values = ss_match_values(client_key, link)
    lower_values = {value.lower() for value in values}
    password = str(client.get("password") or "")
    email = str(client.get("email") or "")
    client_id = str(client.get("id") or client.get("uuid") or "")
    sub_id = str(client.get("subId") or "")
    return (
        password in values
        or email.lower() in lower_values
        or client_id in values
        or sub_id in values
    )


def replace_ss_password(link: str, new_password: str) -> str:
    body, sep, suffix = link[5:].partition("#")
    query_sep = ""
    query = ""
    if "?" in body:
        body, query_sep, query = body.partition("?")
    parsed = parse_ss_link(link)
    if not parsed:
        return link
    link_password = ss_link_password_with_new_client_key(parsed["method"], parsed["password"], new_password)

    if "@" in body:
        user_info, host_part = body.rsplit("@", 1)
        new_user_info = _b64encode_urlsafe(f"{parsed['method']}:{link_password}")
        rebuilt = f"ss://{new_user_info}@{host_part}"
    else:
        decoded = _b64decode_urlsafe(body).decode("utf-8", errors="ignore")
        _, host_part = decoded.rsplit("@", 1)
        new_full = f"{parsed['method']}:{link_password}@{host_part}"
        rebuilt = f"ss://{_b64encode_urlsafe(new_full)}"

    if query_sep:
        rebuilt += f"?{query}"
    if sep:
        rebuilt += f"#{suffix}"
    return rebuilt


def load_settings(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def api_success(data: Any) -> bool:
    return isinstance(data, dict) and data.get("success") is True


def api_obj(data: Any) -> Any:
    if isinstance(data, dict):
        return data.get("obj")
    return None


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class XUIClient:
    def __init__(self, config: PanelConfig):
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Host": config.domain, **HEADERS})
        self.last_error = ""
        if config.token:
            self.session.headers.update({"Authorization": f"Bearer {config.token}"})

    def login(self) -> bool:
        if self.config.token:
            return True
        if not self.config.username or not self.config.password:
            return False

        csrf = self._csrf_token()
        headers = {}
        if csrf:
            headers["x-csrf-token"] = csrf
            self.session.headers.update({"x-csrf-token": csrf})
        try:
            resp = self.session.post(
                f"{self.base_url}/login",
                data={"username": self.config.username, "password": self.config.password},
                headers=headers,
                timeout=8,
                verify=False,
            )
        except requests.RequestException:
            self.last_error = "خطا در اتصال به صفحه لاگین پنل"
            return False

        if resp.status_code != 200:
            self.last_error = f"لاگین پنل ناموفق بود: HTTP {resp.status_code}"
            return False
        try:
            data = resp.json()
            if isinstance(data, dict) and "success" in data:
                if data.get("success"):
                    return True
                self.last_error = str(data.get("msg") or data.get("message") or "نام کاربری یا رمز پنل اشتباه است")
                return False
        except ValueError:
            pass
        ok = "username" not in resp.text.lower()
        if not ok:
            self.last_error = "نام کاربری یا رمز پنل اشتباه است"
        return ok

    def _csrf_token(self) -> str | None:
        try:
            resp = self.session.get(f"{self.base_url}/csrf-token", timeout=5, verify=False)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    for key in ("csrfToken", "csrf_token", "token"):
                        if data.get(key):
                            return str(data[key])
                    obj = data.get("obj")
                    if isinstance(obj, str):
                        return obj
                    if isinstance(obj, dict):
                        for key in ("csrfToken", "csrf_token", "token"):
                            if obj.get(key):
                                return str(obj[key])
                except ValueError:
                    token_match = re.search(r'content=["\']([^"\']+)["\']', resp.text)
                    if token_match:
                        return token_match.group(1)
        except requests.RequestException:
            pass

        try:
            resp = self.session.get(self.base_url, timeout=5, verify=False)
            token_match = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', resp.text)
            if token_match:
                return token_match.group(1)
        except requests.RequestException:
            pass
        return None

    def api(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | None:
        try:
            resp = self.session.request(
                method,
                f"{self.base_url}/panel/api{path}",
                timeout=kwargs.pop("timeout", 8),
                verify=False,
                **kwargs,
            )
            if resp.status_code == 404:
                self.last_error = f"مسیر API پیدا نشد: {path}"
                return None
            data = resp.json()
            if isinstance(data, dict):
                if resp.status_code >= 400:
                    self.last_error = str(data.get("msg") or data.get("message") or f"HTTP {resp.status_code}")
                elif data.get("success") is False:
                    self.last_error = str(data.get("msg") or data.get("message") or "درخواست API توسط پنل رد شد")
                return data
            self.last_error = f"پاسخ API معتبر نیست: {path}"
            return None
        except requests.RequestException as exc:
            self.last_error = f"خطای ارتباط با API پنل: {exc}"
            return None
        except ValueError:
            self.last_error = f"پاسخ JSON معتبر نیست: {path}"
            return None

    def list_new_clients(self) -> list[dict[str, Any]] | None:
        data = self.api("GET", "/clients/list")
        if not api_success(data):
            return None
        obj = api_obj(data)
        return obj if isinstance(obj, list) else []

    def list_legacy_inbounds(self) -> list[dict[str, Any]] | None:
        data = self.api("GET", "/inbounds/list")
        if not api_success(data):
            return None
        obj = api_obj(data)
        return obj if isinstance(obj, list) else []

    def online_emails(self) -> set[str]:
        for path in ("/clients/onlines", "/inbounds/onlines"):
            data = self.api("POST", path, timeout=4)
            if api_success(data):
                obj = api_obj(data)
                if isinstance(obj, list):
                    return {str(item) for item in obj}
        return set()

    def find_new_client(self, proto: str, client_key: str, link: str | None = None) -> dict[str, Any] | None:
        clients = self.list_new_clients()
        if clients is None:
            return None
        for client in clients:
            if proto == "vless" and str(client.get("uuid") or client.get("id") or "") == client_key:
                return client
            if proto == "ss" and ss_client_matches(client, client_key, link):
                return client
        return None

    def get_new_client_detail(self, email: str) -> dict[str, Any] | None:
        if not email:
            return None
        data = self.api("GET", f"/clients/get/{quote(email, safe='')}")
        if not api_success(data):
            return None
        obj = api_obj(data)
        if not isinstance(obj, dict):
            return None
        client = obj.get("client")
        if isinstance(client, dict):
            inbound_ids = obj.get("inboundIds")
            if isinstance(inbound_ids, list):
                client["inboundIds"] = inbound_ids
            return client
        return None

    def build_new_client_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record.get("uuid") or record.get("id") or "",
            "security": record.get("security") or "auto",
            "password": record.get("password") or "",
            "flow": record.get("flow") or "",
            "auth": record.get("auth") or "",
            "email": record.get("email") or "",
            "limitIp": int_value(record.get("limitIp")),
            "totalGB": int_value(record.get("totalGB")),
            "expiryTime": int_value(record.get("expiryTime")),
            "enable": bool(record.get("enable", True)),
            "tgId": int_value(record.get("tgId")),
            "subId": record.get("subId") or "",
            "group": record.get("group") or "",
            "comment": record.get("comment") or "",
            "reset": int_value(record.get("reset")),
            "created_at": int_value(record.get("createdAt") or record.get("created_at")),
        }

    def update_new_client(self, record: dict[str, Any], payload: dict[str, Any]) -> bool:
        email = str(record.get("email") or "")
        if not email:
            return False
        inbound_ids = record.get("inboundIds")
        query = ""
        if isinstance(inbound_ids, list) and inbound_ids:
            query = "?inboundIds=" + ",".join(str(int_value(item)) for item in inbound_ids if int_value(item))
        data = self.api("POST", f"/clients/update/{quote(email, safe='')}{query}", json=payload)
        return api_success(data)


def generate_shadowsocks_key(method: str | None = None) -> str:
    if method == "2022-blake3-aes-128-gcm":
        return base64.b64encode(os.urandom(16)).decode("utf-8")
    if method in ("2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305"):
        return base64.b64encode(os.urandom(32)).decode("utf-8")
    return base64.b64encode(uuid_tool.uuid4().bytes).decode("utf-8")[:24]


def client_usage_from_new_record(client: dict[str, Any], online_emails: set[str]) -> dict[str, Any]:
    traffic = client.get("traffic") if isinstance(client.get("traffic"), dict) else {}
    email = client.get("email") or traffic.get("email") or "-"
    up = int_value(traffic.get("up"))
    down = int_value(traffic.get("down"))
    used = up + down
    total = int_value(traffic.get("total") or client.get("totalGB"))
    exp_t = int_value(traffic.get("expiryTime") or client.get("expiryTime"))
    percent = (used / total) * 100 if total > 0 else 0
    is_expired = (exp_t > 0 and exp_t < int(time.time() * 1000)) or (total > 0 and used >= total)
    exp_s = "نامحدود"
    if exp_t > 0:
        rem = (exp_t / 1000) - time.time()
        exp_s = f"{max(0, int(rem // 86400))} روز" if rem > 0 else "منقضی شده"

    return {
        "email": email,
        "used": format_bytes(used),
        "total": format_bytes(total) if total > 0 else "نامحدود",
        "percent": round(percent, 2),
        "expiry": exp_s,
        "is_enable": bool(client.get("enable", True)) and not is_expired,
        "is_expired": is_expired,
        "is_online": str(email) in online_emails,
    }


def check_new_panel(config: PanelConfig, proto: str, client_key: str, link: str | None = None) -> dict[str, Any] | None:
    api = XUIClient(config)
    if not api.login():
        return None
    client = api.find_new_client(proto, client_key, link)
    if not client:
        return None
    return client_usage_from_new_record(client, api.online_emails())


def check_legacy_panel(config: PanelConfig, proto: str, client_key: str, link: str | None = None) -> dict[str, Any] | None:
    api = XUIClient(config)
    if not api.login():
        return None
    inbounds = api.list_legacy_inbounds()
    if inbounds is None:
        return None
    for inbound in inbounds:
        if proto == "vless" and inbound.get("protocol") != "vless":
            continue
        if proto == "ss" and inbound.get("protocol") != "shadowsocks":
            continue

        settings = load_settings(inbound.get("settings"))
        for client in settings.get("clients", []):
            if not isinstance(client, dict):
                continue
            if proto == "vless" and client.get("id") != client_key:
                continue
            if proto == "ss" and not ss_client_matches(client, client_key, link):
                continue

            email = client.get("email")
            stats = next((stat for stat in inbound.get("clientStats", []) if stat.get("email") == email), {})
            used = int_value(stats.get("up")) + int_value(stats.get("down"))
            total = int_value(stats.get("total") or client.get("totalGB"))
            exp_t = int_value(stats.get("expiryTime") or client.get("expiryTime"))
            percent = (used / total) * 100 if total > 0 else 0
            is_expired = (exp_t > 0 and exp_t < int(time.time() * 1000)) or (total > 0 and used >= total)
            exp_s = "نامحدود"
            if exp_t > 0:
                rem = (exp_t / 1000) - time.time()
                exp_s = f"{max(0, int(rem // 86400))} روز" if rem > 0 else "منقضی شده"
            return {
                "email": email,
                "used": format_bytes(used),
                "total": format_bytes(total) if total > 0 else "نامحدود",
                "percent": round(percent, 2),
                "expiry": exp_s,
                "is_enable": bool(client.get("enable", True)) and not is_expired,
                "is_expired": is_expired,
                "is_online": str(email) in api.online_emails(),
            }
    return None


def check_single_panel(config: PanelConfig, proto: str, client_key: str, link: str | None = None) -> dict[str, Any] | None:
    return check_new_panel(config, proto, client_key, link) or check_legacy_panel(config, proto, client_key, link)


def execute_update_new(config: PanelConfig, proto: str, old_key: str, old_link: str) -> tuple[str, str] | None:
    api = XUIClient(config)
    if not api.login():
        return None
    record = api.find_new_client(proto, old_key, old_link)
    if not record:
        return None
    detail = api.get_new_client_detail(str(record.get("email") or ""))
    if detail:
        detail["traffic"] = record.get("traffic")
        record = detail

    payload = api.build_new_client_payload(record)
    if proto == "vless":
        new_key = str(uuid_tool.uuid4())
        payload["id"] = new_key
    else:
        ss_data = parse_ss_link(old_link) or {}
        new_key = generate_shadowsocks_key(ss_data.get("method"))
        payload["password"] = new_key

    if api.update_new_client(record, payload):
        return new_key, str(record.get("email") or "")
    return None


def execute_update_legacy(config: PanelConfig, proto: str, old_key: str, old_link: str) -> tuple[str, str] | None:
    api = XUIClient(config)
    if not api.login():
        return None
    inbounds = api.list_legacy_inbounds()
    if inbounds is None:
        return None

    for inbound in inbounds:
        if proto == "vless" and inbound.get("protocol") != "vless":
            continue
        if proto == "ss" and inbound.get("protocol") != "shadowsocks":
            continue

        settings = load_settings(inbound.get("settings"))
        for client in settings.get("clients", []):
            if not isinstance(client, dict):
                continue
            if proto == "vless" and client.get("id") != old_key:
                continue
            if proto == "ss" and not ss_client_matches(client, old_key, old_link):
                continue

            updated_client = client.copy()
            email = str(client.get("email") or "")
            if proto == "vless":
                new_key = str(uuid_tool.uuid4())
                updated_client["id"] = new_key
                candidate_ids = [old_key, client.get("id"), email]
            else:
                ss_data = parse_ss_link(old_link) or {}
                new_key = generate_shadowsocks_key(ss_data.get("method"))
                updated_client["password"] = new_key
                candidate_ids = [email, client.get("password"), old_key, *ss_match_values(old_key, old_link)]

            payload = {
                "id": inbound.get("id"),
                "settings": json.dumps({"clients": [updated_client]}, separators=(",", ":")),
            }
            for client_endpoint_id in dict.fromkeys(filter(None, candidate_ids)):
                data = api.api(
                    "POST",
                    f"/inbounds/updateClient/{quote(str(client_endpoint_id), safe='')}",
                    data=payload,
                )
                if api_success(data):
                    return new_key, email
    return None


def execute_update_uuid(config: PanelConfig, proto: str, old_key: str, old_link: str) -> tuple[str, str] | None:
    return execute_update_new(config, proto, old_key, old_link) or execute_update_legacy(config, proto, old_key, old_link)


def execute_toggle_new(config: PanelConfig, proto: str, client_key: str, link: str | None = None) -> tuple[bool, str] | None:
    api = XUIClient(config)
    if not api.login():
        return None
    record = api.find_new_client(proto, client_key, link)
    if not record:
        return None
    detail = api.get_new_client_detail(str(record.get("email") or ""))
    if detail:
        detail["traffic"] = record.get("traffic")
        record = detail
    payload = api.build_new_client_payload(record)
    new_status = not bool(record.get("enable", True))
    payload["enable"] = new_status
    if api.update_new_client(record, payload):
        return new_status, str(record.get("email") or "")
    return None


def execute_toggle_legacy(config: PanelConfig, proto: str, client_key: str, link: str | None = None) -> tuple[bool, str] | None:
    api = XUIClient(config)
    if not api.login():
        return None
    inbounds = api.list_legacy_inbounds()
    if inbounds is None:
        return None

    for inbound in inbounds:
        if proto == "vless" and inbound.get("protocol") != "vless":
            continue
        if proto == "ss" and inbound.get("protocol") != "shadowsocks":
            continue

        settings = load_settings(inbound.get("settings"))
        for client in settings.get("clients", []):
            if not isinstance(client, dict):
                continue
            if proto == "vless" and client.get("id") != client_key:
                continue
            if proto == "ss" and not ss_client_matches(client, client_key, link):
                continue

            email = str(client.get("email") or "")
            new_status = not bool(client.get("enable", True))
            updated_client = client.copy()
            updated_client["enable"] = new_status
            payload = {
                "id": inbound.get("id"),
                "settings": json.dumps({"clients": [updated_client]}, separators=(",", ":")),
            }
            candidate_ids = (
                [client_key, client.get("id"), email]
                if proto == "vless"
                else [email, client.get("password"), client_key, *ss_match_values(client_key, link)]
            )
            for client_endpoint_id in dict.fromkeys(filter(None, candidate_ids)):
                data = api.api(
                    "POST",
                    f"/inbounds/updateClient/{quote(str(client_endpoint_id), safe='')}",
                    data=payload,
                )
                if api_success(data):
                    return new_status, email
    return None


def execute_toggle_client(config: PanelConfig, proto: str, client_key: str, link: str | None = None) -> tuple[bool, str] | None:
    return execute_toggle_new(config, proto, client_key, link) or execute_toggle_legacy(config, proto, client_key, link)


def panel_search_order(target_domain: str | None) -> list[PanelConfig]:
    configs: list[PanelConfig] = []
    if target_domain and target_domain in PANELS:
        configs.append(PANELS[target_domain])
    configs.extend(conf for domain, conf in PANELS.items() if domain != target_domain)
    return configs


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/check", methods=["POST"])
def api_check():
    link = request.form.get("link", "").strip()
    proto, client_key, domain = parse_config_link(link)
    if not proto or not client_key:
        return jsonify({"success": False, "message": "لینک وارد شده معتبر نیست! (پشتیبانی از VLESS و Shadowsocks)"})

    ordered = panel_search_order(domain)
    if not ordered:
        return jsonify({"success": False, "message": "هیچ پنلی برای بررسی تنظیم نشده است."})

    first, rest = ordered[0], ordered[1:]
    result = check_single_panel(first, proto, client_key, link)
    if result:
        result["success"] = True
        return jsonify(result)

    with ThreadPoolExecutor(max_workers=max(1, len(rest))) as executor:
        futures = {executor.submit(check_single_panel, conf, proto, client_key, link): conf.domain for conf in rest}
        for future in as_completed(futures):
            result = future.result()
            if result:
                result["success"] = True
                return jsonify(result)

    return jsonify({"success": False, "message": "کاربر در هیچ‌کدام از پنل‌ها یافت نشد!"})


@app.route("/api/change", methods=["POST"])
def api_change():
    password = request.form.get("password", "").strip()
    if not password:
        return jsonify({"success": False, "needs_password": True, "message": "لطفاً رمز عبور دسترسی به این بخش را وارد کنید:"})
    if password != CHANGE_SECTION_PASSWORD:
        return jsonify({"success": False, "needs_password": True, "message": "رمز عبور اشتباه است! مجدداً وارد کنید:"})

    old_link = request.form.get("link", "").strip()
    proto, old_key, target_domain = parse_config_link(old_link)
    if not proto or not old_key:
        return jsonify({"success": False, "message": "لینک معتبر نیست!"})

    new_key = email = None
    for config in panel_search_order(target_domain):
        res = execute_update_uuid(config, proto, old_key, old_link)
        if res:
            new_key, email = res
            break

    if not new_key:
        return jsonify({"success": False, "message": "کلاینت پیدا نشد یا API پنل اجازه ثبت تغییرات را نداد."})

    if proto == "vless":
        new_link = old_link.replace(old_key, new_key, 1)
    else:
        new_link = replace_ss_password(old_link, new_key)

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(new_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return jsonify({"success": True, "email": email, "new_link": new_link, "qr": qr_base64})


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    link = request.form.get("link", "").strip()
    proto, client_key, target_domain = parse_config_link(link)
    if not proto or not client_key:
        return jsonify({"success": False, "message": "لینک کانفیگ معتبر نیست!"})

    new_status = email = None
    for config in panel_search_order(target_domain):
        res = execute_toggle_client(config, proto, client_key, link)
        if res is not None:
            new_status, email = res
            break

    if new_status is None:
        return jsonify({"success": False, "message": "کلاینت در پنل‌ها جهت تغییر وضعیت پیدا نشد."})

    return jsonify({"success": True, "email": email, "current_status": new_status})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "80")))
