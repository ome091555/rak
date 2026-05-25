import csv
import io
import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from flask import Flask, redirect, render_template_string, request, session, url_for, jsonify, Response, send_file

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

JST = timezone(timedelta(hours=9))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rak-secret-2026')
DATABASE = os.environ.get('DATABASE', 'rak.db')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(DATABASE)), 'uploads')

# ── DB ────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sport TEXT DEFAULT '',
            team_code TEXT UNIQUE NOT NULL,
            admin_password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_time TEXT DEFAULT '',
            location TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rsvps (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(event_id, member_name)
        );
        CREATE TABLE IF NOT EXISTS notices (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reads (
            notice_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            read_at TEXT NOT NULL,
            PRIMARY KEY(notice_id, member_name)
        );
        CREATE TABLE IF NOT EXISTS members (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            name TEXT NOT NULL,
            number TEXT DEFAULT '',
            position TEXT DEFAULT '',
            joined_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fees (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            due_date TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fee_payments (
            id TEXT PRIMARY KEY,
            fee_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            paid INTEGER DEFAULT 0,
            paid_at TEXT DEFAULT '',
            UNIQUE(fee_id, member_name)
        );
        CREATE TABLE IF NOT EXISTS surveys (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS survey_options (
            id TEXT PRIMARY KEY,
            survey_id TEXT NOT NULL,
            label TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS survey_answers (
            id TEXT PRIMARY KEY,
            survey_id TEXT NOT NULL,
            option_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            answered_at TEXT NOT NULL,
            UNIQUE(survey_id, member_name)
        );
        CREATE TABLE IF NOT EXISTS ai_templates (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_forms (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            deadline TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_form_fields (
            id TEXT PRIMARY KEY,
            form_id TEXT NOT NULL,
            label TEXT NOT NULL,
            field_type TEXT DEFAULT 'text',
            options TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS order_responses (
            id TEXT PRIMARY KEY,
            form_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(form_id, member_name)
        );
        CREATE TABLE IF NOT EXISTS order_response_values (
            id TEXT PRIMARY KEY,
            response_id TEXT NOT NULL,
            field_id TEXT NOT NULL,
            value TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS order_form_photos (
            id TEXT PRIMARY KEY,
            form_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT DEFAULT 'image/jpeg',
            uploaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS app_feedback (
            id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    ''')
    conn.commit()
    conn.close()

init_db()

# ── Helpers ───────────────────────────────────────────────────────

def new_id():
    return str(uuid.uuid4())[:8]

def now_str():
    return datetime.now(JST).strftime('%Y-%m-%d %H:%M')

def csv_response(csv_str, filename):
    import urllib.parse
    encoded_name = urllib.parse.quote(filename.encode('utf-8'))
    return Response(
        csv_str.encode('utf-8-sig'),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}"}
    )

def get_team(code):
    conn = get_db()
    t = conn.execute('SELECT * FROM teams WHERE team_code=?', (code.upper(),)).fetchone()
    conn.close()
    return t

def is_admin(code):
    return session.get(f'admin_{code}') is True

def get_member(code):
    return session.get(f'member_{code}', '')

def fmt_date(s):
    try:
        d = datetime.strptime(s, '%Y-%m-%d')
        wd = ['月','火','水','木','金','土','日'][d.weekday()]
        return f"{d.month}/{d.day}（{wd}）"
    except:
        return s

def fmt_datetime(s):
    try:
        d = datetime.strptime(s, '%Y-%m-%d %H:%M')
        return d.strftime('%-m/%-d %H:%M')
    except:
        return s

# ── Base CSS & layout ─────────────────────────────────────────────

FONT = ''

# Rak brand mark: top-right bar → diagonal → bottom bar (flowing/easy)
NAV_MARK = (
    '<svg viewBox="0 0 100 100" width="18" height="18" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M76,28 L44,28 L22,72 L66,72" stroke="white" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)
FAVICON_LINK = (
    '<link rel="icon" href="data:image/svg+xml,'
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<rect width='100' height='100' rx='22' fill='%232563eb'/>"
    "<path d='M76,28 L44,28 L22,72 L66,72' stroke='white' stroke-width='11' stroke-linecap='round' stroke-linejoin='round' fill='none'/>"
    "</svg>"
    '"><meta name="theme-color" content="#2563eb">'
)

ICONS = {
    'schedule': '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="14" height="13" rx="2"/><path d="M7 2v4M13 2v4M3 8h14"/></svg>',
    'notices':  '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 9c0-2.8 2.2-5 5-5s5 2.2 5 5v3l1.5 2.5h-13L5 12V9z"/><path d="M8.5 17.5a1.5 1.5 0 003 0"/></svg>',
    'members':  '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="6" r="3"/><path d="M2 18c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="15" cy="7" r="2.5"/><path d="M18 18c0-2.7-1.5-5-3.5-6"/></svg>',
    'fees':     '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="10" cy="10" r="7"/><path d="M10 6v8M7.5 8c.5-1.5 5-1.5 5 1.5 0 2.5-5 1.5-5 4 0 2 4.5 1.5 5 0"/></svg>',
    'orders':   '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="5" y="2" width="10" height="16" rx="2"/><path d="M8 7h4M8 10.5h4M8 14h2.5"/></svg>',
    'admin':    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="10" cy="10" r="2.5"/><path d="M10 2v2.5M10 15.5V18M2 10h2.5M15.5 10H18M4.9 4.9l1.8 1.8M13.3 13.3l1.8 1.8M4.9 15.1l1.8-1.8M13.3 6.7l1.8-1.8"/></svg>',
    'ai':       '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2.5l1.8 5 5.2 2-5.2 2-1.8 5-1.8-5-5.2-2 5.2-2z"/></svg>',
    'ask':      '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 12a2 2 0 01-2 2H6l-3 3V5a2 2 0 012-2h10a2 2 0 012 2v7z"/></svg>',
}

CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",sans-serif;background:#f5f7fb;color:#1a1a1a;font-size:16px;line-height:1.7;min-height:100vh}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
.nav{background:#fff;border-bottom:1px solid #e8eaf0;padding:0 16px;height:52px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:50}
.nav-logo{font-weight:900;font-size:18px;color:#2563eb;display:flex;align-items:center;gap:6px}
.nav-icon{width:28px;height:28px;background:#2563eb;border-radius:7px;color:#fff;font-size:13px;font-weight:900;display:flex;align-items:center;justify-content:center}
.nav-team{font-size:13px;color:#555;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px}
.nav-links-desktop{display:flex;gap:12px;margin-left:auto;align-items:center}
.nav-links-desktop a{font-size:13px;color:#555;padding:6px 10px;border-radius:8px}
.nav-links-desktop a:hover{background:#eff6ff;color:#2563eb;text-decoration:none}
.nav-links-desktop a.active{color:#2563eb;font-weight:700}
.bottom-nav{display:none;position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e8eaf0;z-index:100;padding-bottom:env(safe-area-inset-bottom,0)}
.bottom-nav a{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:6px 2px;font-size:9px;color:#888;text-decoration:none;gap:2px;min-height:52px}
.bottom-nav a.active{color:#2563eb}
.bottom-nav a.active .nav-b-icon{color:#2563eb}
.nav-b-icon{display:flex;align-items:center;justify-content:center}
.nav-b-icon svg{width:22px;height:22px}
.nav-d-icon{display:inline-flex;vertical-align:-3px;margin-right:4px}
.nav-d-icon svg{width:15px;height:15px}
.container{max-width:680px;margin:0 auto;padding:20px 14px}
.card{background:#fff;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:14px;border:1px solid #eaecf2}
.card-sm{background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #eaecf2;margin-bottom:8px}
h1{font-size:21px;font-weight:900;margin-bottom:4px}
h2{font-size:17px;font-weight:700;margin-bottom:12px}
h3{font-size:15px;font-weight:700}
label{display:block;font-size:12px;font-weight:700;color:#2563eb;margin-bottom:5px;margin-top:14px}
label:first-of-type{margin-top:0}
input[type=text],input[type=password],input[type=date],input[type=time],textarea,select{width:100%;border:1.5px solid #dde0ea;border-radius:10px;padding:11px 14px;font-size:16px;outline:none;font-family:inherit;background:#fafbff}
input:focus,textarea:focus,select:focus{border-color:#2563eb;background:#fff}
textarea{resize:vertical;min-height:80px}
.btn{display:inline-block;padding:12px 22px;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;border:none;font-family:inherit;transition:.12s;text-decoration:none;text-align:center}
.btn-blue{background:#2563eb;color:#fff}
.btn-blue:hover{background:#1d4ed8;text-decoration:none;color:#fff}
.btn-outline{background:#fff;color:#2563eb;border:1.5px solid #2563eb}
.btn-outline:hover{background:#eff6ff;text-decoration:none}
.btn-gray{background:#f1f4f9;color:#555;border:none}
.btn-gray:hover{background:#e4e8f0;text-decoration:none;color:#555}
.btn-block{display:block;width:100%;margin-top:16px}
.btn-sm{padding:7px 14px;font-size:13px;border-radius:8px}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500}
.badge-green{background:#dcfce7;color:#16a34a}
.badge-red{background:#fee2e2;color:#dc2626}
.badge-gray{background:#f1f4f9;color:#64748b}
.badge-blue{background:#dbeafe;color:#1d4ed8}
.msg-ok{background:#f0fdf4;color:#16a34a;padding:12px 16px;border-radius:10px;margin-bottom:16px;font-weight:500;border:1.5px solid #bbf7d0}
.msg-err{background:#fef2f2;color:#dc2626;padding:12px 16px;border-radius:10px;margin-bottom:16px;font-weight:500}
.section-label{font-size:11px;font-weight:700;letter-spacing:.08em;color:#2563eb;background:#eff6ff;padding:3px 10px;border-radius:20px;display:inline-block;margin-bottom:14px}
.empty{text-align:center;padding:36px 20px;color:#999}
.row{display:flex;align-items:center;gap:10px}
.divider{border:none;border-top:1px solid #eaecf2;margin:16px 0}
@media(max-width:639px){
  .nav-links-desktop{display:none}
  .bottom-nav{display:flex}
  .container{padding-bottom:72px}
}
'''

def page(title, body, code=None, active=None):
    team = get_team(code) if code else None
    team_name = team['name'] if team else ''
    admin = is_admin(code) if code else False
    member = get_member(code) if code else ''

    desktop_nav = ''
    bottom_nav = ''
    if code:
        tabs = [
            ('schedule', 'schedule', '予定',    f'/t/{code}/schedule'),
            ('notices',  'notices',  '連絡',    f'/t/{code}/notices'),
            ('members',  'members',  'メンバー', f'/t/{code}/members'),
            ('fees',     'fees',     '集金',    f'/t/{code}/fees'),
            ('orders',   'orders',   '注文',    f'/t/{code}/orders'),
        ]
        if admin:
            tabs.append(('admin', 'admin', '管理', f'/t/{code}/admin/dash'))

        for key, icon_key, label, url in tabs:
            cls = 'active' if active == key else ''
            ico = ICONS[icon_key]
            desktop_nav += f'<a href="{url}" class="{cls}"><span class="nav-d-icon">{ico}</span>{label}</a>'
            bottom_nav += f'<a href="{url}" class="{cls}"><span class="nav-b-icon">{ico}</span><span>{label}</span></a>'

        if admin:
            ai_cls = 'active' if active == 'ai' else ''
            desktop_nav += f'<a href="/t/{code}/admin/ai" class="{ai_cls}"><span class="nav-d-icon">{ICONS["ai"]}</span>AI</a>'
        elif member:
            desktop_nav += f'<span style="font-size:12px;color:#888;padding:6px 10px">👤 {member}</span>'

        bottom_nav = f'<nav class="bottom-nav">{bottom_nav}</nav>'

    return render_template_string(f'''<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
{FAVICON_LINK}
{FONT}<title>{title} | Rak</title>
<style>{CSS}</style></head><body>
<nav class="nav">
  <a class="nav-logo" href="{"/t/"+code if code else "/"}">
    <div class="nav-icon">{NAV_MARK}</div>Rak
  </a>
  {f'<span class="nav-team">{team_name}</span>' if team_name else ''}
  <div class="nav-links-desktop">{desktop_nav}</div>
</nav>
{body}
{bottom_nav}
</body></html>''')


# ── Home / Create ─────────────────────────────────────────────────

@app.route('/')
def home():
    body = '''
<div class="container" style="max-width:480px;padding-top:60px">
  <div style="text-align:center;margin-bottom:32px">
    <div style="font-size:40px;font-weight:900;color:#2563eb;margin-bottom:8px">Rak</div>
    <div style="color:#555;font-size:15px">チーム運営の「めんどくさい」を、ぜんぶラクに。</div>
  </div>
  <div class="card">
    <h2>チームコードで入る</h2>
    <form method="POST" action="/join">
      <label>チームコード</label>
      <input type="text" name="code" placeholder="例：ABC123" style="text-transform:uppercase;letter-spacing:.1em;font-size:18px;font-weight:700">
      <button class="btn btn-blue btn-block" type="submit">入る →</button>
    </form>
  </div>
  <div style="text-align:center;color:#888;font-size:13px;margin:16px 0">または</div>
  <div class="card">
    <h2>新しいチームを作る</h2>
    <p style="font-size:13px;color:#666;margin-bottom:16px">管理者として新しいチームを登録します</p>
    <a href="/create" class="btn btn-outline" style="display:block;text-align:center">チームを作成する →</a>
  </div>
</div>'''
    return page('ホーム', body)

@app.route('/join', methods=['POST'])
def join():
    code = request.form.get('code', '').strip().upper()
    team = get_team(code)
    if not team:
        return redirect('/')
    return redirect(url_for('team_portal', code=code))

@app.route('/create', methods=['GET', 'POST'])
def create_team():
    error = ''
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()
        if not name or not password:
            error = 'チーム名とパスワードを入力してください'
        else:
            team_id = new_id()
            code = new_id().upper()[:6]
            conn = get_db()
            conn.execute(
                'INSERT INTO teams VALUES (?,?,?,?,?,?)',
                (team_id, name, '', code, password, now_str())
            )
            conn.commit()
            conn.close()
            session[f'admin_{code}'] = True
            return redirect(url_for('admin_dash', code=code, created='1'))

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>チームを作成</h1>
    <p style="color:#666;font-size:13px;margin-bottom:16px">作成後、メンバーに共有するチームコードが発行されます</p>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>チーム名・グループ名 *</label>
      <input type="text" name="name" placeholder="例：FCランウェイズ、○○部、△△サークル" required>
      <label>管理者パスワード *</label>
      <input type="password" name="password" placeholder="管理者だけが知るパスワード" required>
      <div style="font-size:12px;color:#888;margin-top:6px">※メンバーには共有しないでください</div>
      <button class="btn btn-blue btn-block" type="submit">チームを作成してコードを発行 →</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/" style="font-size:13px;color:#888">← トップに戻る</a></div>
</div>'''
    return page('チーム作成', body)


# ── Member portal ─────────────────────────────────────────────────

@app.route('/t/<code>')
def team_portal(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    if not member and not is_admin(code):
        body = f'''
<div class="container" style="max-width:480px;padding-top:60px">
  <div class="card" style="text-align:center">
    <div style="font-size:32px;margin-bottom:8px">👋</div>
    <h1 style="margin-bottom:6px">{team["name"]}</h1>
    <p style="color:#666;font-size:13px;margin-bottom:20px">あなたの名前を入力してください</p>
    <form method="POST" action="/t/{code}/join">
      <input type="text" name="name" placeholder="例：田中 花子" required style="text-align:center;font-size:17px">
      <button class="btn btn-blue btn-block" type="submit">入る →</button>
    </form>
  </div>
</div>'''
        return page(team['name'], body, code)

    return redirect(url_for('schedule', code=code))

@app.route('/t/<code>/join', methods=['POST'])
def member_join(code):
    name = request.form.get('name', '').strip()
    if name:
        session[f'member_{code}'] = name
    return redirect(url_for('schedule', code=code))


# ── Schedule ──────────────────────────────────────────────────────

def build_calendar(year, month, event_dates):
    import calendar
    cal = calendar.monthcalendar(year, month)
    wd_labels = ['月','火','水','木','金','土','日']
    header = ''.join(f'<div style="text-align:center;font-size:11px;font-weight:700;color:#888;padding:4px 0">{d}</div>' for d in wd_labels)
    rows = ''
    for week in cal:
        for day in week:
            if day == 0:
                rows += '<div></div>'
            else:
                date_str = f'{year}-{month:02d}-{day:02d}'
                has_event = date_str in event_dates
                today_str = datetime.now(JST).strftime('%Y-%m-%d')
                is_today = date_str == today_str
                dot = '<div style="width:5px;height:5px;border-radius:50%;background:#2563eb;margin:2px auto 0"></div>' if has_event else ''
                bg = 'background:#2563eb;color:#fff;' if is_today else ('background:#eff6ff;' if has_event else '')
                cursor = 'pointer' if has_event else 'default'
                fw = '700' if (is_today or has_event) else '400'
                onclick = f'onclick="scrollToDate(\'{date_str}\')"' if has_event else ''
                rows += f'<div style="text-align:center;padding:5px 2px;border-radius:8px;cursor:{cursor};{bg}" {onclick}><div style="font-size:13px;font-weight:{fw}">{day}</div>{dot}</div>'
    return f'''
<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px">
  {header}{rows}
</div>'''

@app.route('/t/<code>/schedule')
def schedule(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    now = datetime.now(JST)
    today = now.strftime('%Y-%m-%d')

    try:
        vy = int(request.args.get('y', now.year))
        vm = int(request.args.get('m', now.month))
        vm = max(1, min(12, vm))
    except Exception:
        vy, vm = now.year, now.month

    month_start = f'{vy}-{vm:02d}-01'
    ny, nm = (vy + 1, 1) if vm == 12 else (vy, vm + 1)
    month_end = f'{ny}-{nm:02d}-01'
    py, pm = (vy - 1, 12) if vm == 1 else (vy, vm - 1)

    conn = get_db()
    all_events = conn.execute(
        'SELECT * FROM events WHERE team_id=? AND event_date>=? AND event_date<? ORDER BY event_date,event_time',
        (team['id'], month_start, month_end)
    ).fetchall()

    fees_in_month = conn.execute(
        "SELECT * FROM fees WHERE team_id=? AND due_date>=? AND due_date<? AND due_date!='' ORDER BY due_date",
        (team['id'], month_start, month_end)
    ).fetchall()

    event_dates = set(ev['event_date'] for ev in all_events) | set(f['due_date'] for f in fees_in_month)
    calendar_html = build_calendar(vy, vm, event_dates)

    event_cards = ''
    for ev in all_events:
        rsvps = conn.execute('SELECT * FROM rsvps WHERE event_id=?', (ev['id'],)).fetchall()
        attending = sum(1 for r in rsvps if r['status'] == 'attending')
        absent = sum(1 for r in rsvps if r['status'] == 'absent')
        my_rsvp = ''
        if member:
            r = conn.execute('SELECT status FROM rsvps WHERE event_id=? AND member_name=?',
                             (ev['id'], member)).fetchone()
            my_rsvp = r['status'] if r else ''
        rsvp_btns = ''
        if member:
            rsvp_btns = f'''
            <form method="POST" action="/t/{code}/rsvp/{ev['id']}" style="display:flex;gap:8px;margin-top:12px">
              <button name="status" value="attending" class="btn btn-sm {'btn-blue' if my_rsvp=='attending' else 'btn-outline'}" type="submit">出席</button>
              <button name="status" value="absent" class="btn btn-sm btn-gray" type="submit" style="{'background:#fee2e2;color:#dc2626' if my_rsvp=='absent' else ''}">欠席</button>
            </form>'''
        event_cards += f'''
        <div class="card-sm" id="ev-{ev['event_date']}">
          <div class="row" style="flex-wrap:wrap;gap:6px">
            <div style="flex:1;min-width:0">
              <div style="font-weight:700;font-size:16px">{ev['title']}</div>
              <div style="font-size:13px;color:#666;margin-top:2px">{fmt_date(ev['event_date'])}{' ' + ev['event_time'] if ev['event_time'] else ''}{('　' + ev['location']) if ev['location'] else ''}</div>
            </div>
            <div style="display:flex;gap:6px;align-items:center">
              <span class="badge badge-green">出席 {attending}</span>
              <span class="badge badge-red">欠席 {absent}</span>
            </div>
          </div>
          {f'<div style="font-size:13px;color:#666;margin-top:8px;background:#f8faff;padding:8px 12px;border-radius:8px">{ev["note"]}</div>' if ev['note'] else ''}
          {rsvp_btns}
        </div>'''

    fee_cards = ''
    for f in fees_in_month:
        paid_row = conn.execute('SELECT paid FROM fee_payments WHERE fee_id=? AND member_name=?',
                                (f['id'], member)).fetchone() if member else None
        paid = paid_row['paid'] if paid_row else None
        status_badge = ''
        if member:
            status_badge = '<span class="badge badge-green">支払済</span>' if paid else '<span class="badge badge-red">未払い</span>'
        fee_cards += f'''
        <div class="card-sm" id="ev-{f['due_date']}" style="border-left:3px solid #f59e0b;background:#fffbeb">
          <div class="row" style="justify-content:space-between;align-items:center">
            <div>
              <div style="font-weight:700">集金期限：{f['title']}</div>
              <div style="font-size:13px;color:#666;margin-top:2px">{fmt_date(f['due_date'])}　¥{f['amount']:,}</div>
            </div>
            {status_badge}
          </div>
        </div>'''

    conn.close()

    is_this_month = (vy == now.year and vm == now.month)
    today_btn = '' if is_this_month else f'<a href="/t/{code}/schedule" style="font-size:12px;color:#2563eb;padding:3px 10px;border:1.5px solid #2563eb;border-radius:8px;text-decoration:none">今月</a>'
    new_btn = f'<a href="/t/{code}/admin/events/new" class="btn btn-blue btn-sm">＋ 追加</a>' if admin else ''
    combined = (event_cards + fee_cards) or '<div class="empty card">この月の予定はありません</div>'

    body = f'''
<div class="container">
  <div class="row" style="margin-bottom:16px">
    <div><span class="section-label">スケジュール</span></div>
    {new_btn}
  </div>
  <div class="card" style="margin-bottom:16px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <a href="/t/{code}/schedule?y={py}&m={pm}" style="width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:8px;background:#f1f4f9;color:#333;font-size:18px;text-decoration:none;flex-shrink:0">‹</a>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-weight:700;font-size:16px">{vy}年{vm}月</span>
        {today_btn}
      </div>
      <a href="/t/{code}/schedule?y={ny}&m={nm}" style="width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:8px;background:#f1f4f9;color:#333;font-size:18px;text-decoration:none;flex-shrink:0">›</a>
    </div>
    {calendar_html}
  </div>
  {combined}
</div>
<script>
function scrollToDate(date) {{
  var el = document.getElementById('ev-' + date);
  if (el) el.scrollIntoView({{behavior:'smooth', block:'center'}});
}}
</script>'''
    return page('スケジュール', body, code, active='schedule')

@app.route('/t/<code>/rsvp/<event_id>', methods=['POST'])
def rsvp(code, event_id):
    member = get_member(code)
    if not member:
        return redirect(url_for('team_portal', code=code))
    status = request.form.get('status', 'attending')
    conn = get_db()
    conn.execute('''
        INSERT INTO rsvps (id,event_id,member_name,status,updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(event_id,member_name) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at
    ''', (new_id(), event_id, member, status, now_str()))
    conn.commit()
    conn.close()
    return redirect(url_for('schedule', code=code))


# ── Notices ───────────────────────────────────────────────────────

@app.route('/t/<code>/notices')
def notices(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    ns = conn.execute(
        'SELECT * FROM notices WHERE team_id=? ORDER BY created_at DESC',
        (team['id'],)
    ).fetchall()

    cards = ''
    for n in ns:
        read_count = conn.execute('SELECT COUNT(*) FROM reads WHERE notice_id=?', (n['id'],)).fetchone()[0]
        is_read = bool(conn.execute('SELECT 1 FROM reads WHERE notice_id=? AND member_name=?',
                                    (n['id'], member)).fetchone()) if member else True
        cards += f'''
        <a href="/t/{code}/notices/{n['id']}" style="text-decoration:none;display:block">
          <div class="card-sm" style="{'opacity:.7' if is_read else ''}">
            <div class="row">
              <div style="flex:1">
                <div style="font-weight:700;color:#1a1a1a">{'📌 ' if not is_read else ''}{n['title']}</div>
                <div style="font-size:12px;color:#888;margin-top:2px">{fmt_datetime(n['created_at'])}</div>
              </div>
              <div>
                {'<span class="badge badge-blue">NEW</span>' if not is_read else f'<span class="badge badge-gray">既読 {read_count}</span>'}
              </div>
            </div>
          </div>
        </a>'''
    conn.close()

    new_btn = f'<a href="/t/{code}/admin/notices/new" class="btn btn-blue btn-sm">＋ お知らせ作成</a>' if admin else ''
    body = f'''
<div class="container">
  <div class="row" style="margin-bottom:16px">
    <div><span class="section-label">📢 お知らせ</span></div>
    {new_btn}
  </div>
  {cards if ns else '<div class="empty card">📭<br>お知らせはまだありません</div>'}
</div>'''
    return page('お知らせ', body, code, active='notices')

@app.route('/t/<code>/notices/<notice_id>')
def notice_detail(code, notice_id):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    n = conn.execute('SELECT * FROM notices WHERE id=? AND team_id=?', (notice_id, team['id'])).fetchone()
    if not n:
        conn.close()
        return redirect(url_for('notices', code=code))

    if member:
        conn.execute('''
            INSERT OR IGNORE INTO reads (notice_id,member_name,read_at) VALUES (?,?,?)
        ''', (notice_id, member, now_str()))
        conn.commit()

    readers = conn.execute('SELECT member_name, read_at FROM reads WHERE notice_id=? ORDER BY read_at', (notice_id,)).fetchall()
    conn.close()

    reader_list = ''
    if admin:
        reader_list = ''.join(f'<div style="font-size:13px;padding:6px 0;border-bottom:1px solid #f0f0f0;color:#555">{r["member_name"]} <span style="color:#aaa;font-size:11px">{fmt_datetime(r["read_at"])}</span></div>' for r in readers)
        reader_list = f'<hr class="divider"><div style="font-size:12px;font-weight:700;color:#2563eb;margin-bottom:8px">既読 {len(readers)}名</div>{reader_list}'

    body = f'''
<div class="container">
  <div class="card">
    <div style="font-size:12px;color:#888;margin-bottom:8px">{fmt_datetime(n['created_at'])}</div>
    <h1 style="margin-bottom:16px">{n['title']}</h1>
    <div style="white-space:pre-wrap;line-height:1.8;color:#333">{n['body']}</div>
    {reader_list}
  </div>
  <div style="text-align:center"><a href="/t/{code}/notices" style="font-size:13px;color:#888">← お知らせ一覧</a></div>
</div>'''
    return page(n['title'], body, code, active='notices')


# ── Admin login ───────────────────────────────────────────────────

@app.route('/t/<code>/admin', methods=['GET', 'POST'])
def admin_login(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    if is_admin(code):
        return redirect(url_for('admin_dash', code=code))

    error = ''
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == team['admin_password']:
            session[f'admin_{code}'] = True
            return redirect(url_for('admin_dash', code=code))
        error = 'パスワードが違います'

    body = f'''
<div class="container" style="max-width:400px;padding-top:60px">
  <div class="card">
    <h1 style="margin-bottom:4px">管理者ログイン</h1>
    <p style="color:#666;font-size:13px;margin-bottom:16px">{team['name']}</p>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>パスワード</label>
      <input type="password" name="password" autofocus required>
      <button class="btn btn-blue btn-block" type="submit">ログイン</button>
    </form>
  </div>
</div>'''
    return page('管理者ログイン', body, code)

@app.route('/t/<code>/admin/logout')
def admin_logout(code):
    session.pop(f'admin_{code}', None)
    return redirect(url_for('team_portal', code=code))


# ── Admin dashboard ───────────────────────────────────────────────

@app.route('/t/<code>/admin/dash')
def admin_dash(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    created = request.args.get('created') == '1'

    conn = get_db()
    today = datetime.now(JST).strftime('%Y-%m-%d')
    events = conn.execute(
        'SELECT * FROM events WHERE team_id=? AND event_date>=? ORDER BY event_date LIMIT 3',
        (team['id'], today)
    ).fetchall()
    notices = conn.execute(
        'SELECT * FROM notices WHERE team_id=? ORDER BY created_at DESC LIMIT 3',
        (team['id'],)
    ).fetchall()

    # 集金未払いリスト
    fees = conn.execute('SELECT * FROM fees WHERE team_id=? ORDER BY due_date, created_at', (team['id'],)).fetchall()
    unpaid_summary = []
    for f in fees:
        members_for_fee = conn.execute('SELECT * FROM members WHERE team_id=? ORDER BY name', (team['id'],)).fetchall()
        for m in members_for_fee:
            p = conn.execute('SELECT paid FROM fee_payments WHERE fee_id=? AND member_name=?', (f['id'], m['name'])).fetchone()
            if not p or not p['paid']:
                unpaid_summary.append({'fee_title': f['title'], 'member': m['name'], 'amount': f['amount'], 'due_date': f['due_date'], 'fee_id': f['id']})

    members_all = conn.execute('SELECT name FROM members WHERE team_id=?', (team['id'],)).fetchall()
    member_names = [m['name'] for m in members_all]

    def get_no_answer(ev_id):
        answered = set(r['member_name'] for r in conn.execute('SELECT member_name FROM rsvps WHERE event_id=?', (ev_id,)).fetchall())
        return [n for n in member_names if n not in answered]

    event_rows = ''
    for ev in events:
        no_answer = get_no_answer(ev['id'])
        no_answer_html = ''
        if no_answer:
            names_str = '、'.join(no_answer[:5])
            more = f' 他{len(no_answer)-5}名' if len(no_answer) > 5 else ''
            no_answer_html = f'<div style="font-size:11px;color:#dc2626;margin-top:4px">未回答：{names_str}{more}</div>'
        event_rows += f'''
    <div class="card-sm row" style="justify-content:space-between;align-items:flex-start">
      <div style="flex:1">
        <div style="font-weight:700">{ev['title']}</div>
        <div style="font-size:12px;color:#888">{fmt_date(ev['event_date'])}{' ' + ev['event_time'] if ev['event_time'] else ''}</div>
        {no_answer_html}
      </div>
      <a href="/t/{code}/admin/events/{ev['id']}" class="btn btn-sm btn-outline" style="margin-left:8px;flex-shrink:0">詳細</a>
    </div>'''
    event_rows = event_rows or '<div class="empty">予定なし</div>'

    conn.close()

    notice_rows = ''.join(f'''
    <div class="card-sm row" style="justify-content:space-between">
      <div>
        <div style="font-weight:700">{n['title']}</div>
        <div style="font-size:12px;color:#888">{fmt_datetime(n['created_at'])}</div>
      </div>
      <a href="/t/{code}/notices/{n['id']}" class="btn btn-sm btn-outline">確認</a>
    </div>''' for n in notices) or '<div class="empty">お知らせなし</div>'

    body = f'''
<div class="container">
  {'<div class="msg-ok">✅ チームを作成しました！チームコードをメンバーに共有してください。</div>' if created else ''}

  <div class="card" style="background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;border:none">
    <div style="font-size:13px;opacity:.8;margin-bottom:4px">チームコード</div>
    <div style="font-size:36px;font-weight:900;letter-spacing:.15em">{code}</div>
    <div style="font-size:13px;opacity:.7;margin-top:4px">このコードをメンバーに共有してください</div>
    <div style="margin-top:12px;font-size:13px;background:rgba(255,255,255,.15);padding:8px 14px;border-radius:8px;word-break:break-all">
      メンバー用URL: {request.host_url}t/{code}
    </div>
  </div>

  <div class="card">
    <div class="row" style="margin-bottom:12px">
      <h2 style="margin:0">📅 直近の予定</h2>
      <a href="/t/{code}/admin/events/new" class="btn btn-sm btn-blue" style="margin-left:auto">＋ 追加</a>
    </div>
    {event_rows}
    <div style="margin-top:10px"><a href="/t/{code}/schedule" style="font-size:13px">すべて見る →</a></div>
  </div>

  <div class="card">
    <div class="row" style="margin-bottom:12px">
      <h2 style="margin:0">📢 最近のお知らせ</h2>
      <a href="/t/{code}/admin/notices/new" class="btn btn-sm btn-blue" style="margin-left:auto">＋ 作成</a>
    </div>
    {notice_rows}
    <div style="margin-top:10px"><a href="/t/{code}/notices" style="font-size:13px">すべて見る →</a></div>
  </div>

  <div class="card">
    <div class="row" style="margin-bottom:12px">
      <h2 style="margin:0">💰 集金 未払いリスト</h2>
      <span class="badge {'badge-red' if unpaid_summary else 'badge-green'}" style="margin-left:auto">{'未払い ' + str(len(unpaid_summary)) + '件' if unpaid_summary else '全員支払済'}</span>
    </div>
    {''.join(f"""<div class="card-sm row" style="justify-content:space-between;align-items:center;background:#fff9f9">
      <div>
        <div style="font-weight:700;font-size:13px">{u['member']}</div>
        <div style="font-size:12px;color:#888">{u['fee_title']}　¥{u['amount']:,}{('　期限：' + fmt_date(u['due_date'])) if u['due_date'] else ''}</div>
      </div>
      <a href="/t/{code}/admin/fees/{u['fee_id']}" class="btn btn-sm btn-outline">管理</a>
    </div>""" for u in unpaid_summary[:5]) if unpaid_summary else '<div class="empty">未払いなし 🎉</div>'}
    {f'<div style="margin-top:8px;font-size:13px;color:#888">他 {len(unpaid_summary)-5}件…</div>' if len(unpaid_summary) > 5 else ''}
    <div style="margin-top:10px"><a href="/t/{code}/admin/fees" style="font-size:13px">集金管理を見る →</a></div>
  </div>

  <div class="card">
    <h2>👥 メンバー管理</h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">名簿の確認・追加・削除ができます</p>
    <a href="/t/{code}/admin/members" class="btn btn-outline" style="display:block;text-align:center">メンバー一覧を見る →</a>
  </div>

  <div class="card">
    <h2>💰 集金管理</h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">集金項目の作成・支払い状況の管理ができます</p>
    <a href="/t/{code}/admin/fees" class="btn btn-outline" style="display:block;text-align:center">集金管理を見る →</a>
  </div>

  <div class="card">
    <h2>📋 注文フォーム</h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">弁当・ウェアなど、チーム独自の注文フォームを作成してメンバーの回答を集計できます</p>
    <a href="/t/{code}/orders" class="btn btn-outline" style="display:block;text-align:center">注文フォームを見る →</a>
  </div>

  <div class="card">
    <h2>✦ AI文章作成</h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">一言メモから、丁寧な連絡文を自動生成します</p>
    <a href="/t/{code}/admin/ai" class="btn btn-outline" style="display:block;text-align:center">AI文章作成を使う →</a>
  </div>

  <div class="card">
    <h2>📬 Rakへのお問い合わせ</h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">機能の要望・不具合報告・ご意見はこちらから</p>
    <a href="/feedback" class="btn btn-outline" style="display:block;text-align:center">お問い合わせ・要望を送る →</a>
  </div>

  <div style="text-align:right;margin-top:8px">
    <a href="/t/{code}/admin/logout" style="font-size:12px;color:#aaa">ログアウト</a>
  </div>
</div>'''
    return page('管理ダッシュボード', body, code, active='admin')


# ── Admin: events ─────────────────────────────────────────────────

@app.route('/t/<code>/admin/events/new', methods=['GET', 'POST'])
def admin_new_event(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    error = ''

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        date = request.form.get('event_date', '').strip()
        time = request.form.get('event_time', '').strip()
        location = request.form.get('location', '').strip()
        note = request.form.get('note', '').strip()
        if not title or not date:
            error = 'タイトルと日付を入力してください'
        else:
            conn = get_db()
            conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                         (new_id(), team['id'], title, date, time, location, note, now_str()))
            conn.commit()
            conn.close()
            return redirect(url_for('schedule', code=code))

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>予定を追加</h1>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>タイトル *</label>
      <input type="text" name="title" placeholder="例：練習試合 vs FCさくら" required>
      <label>日付 *</label>
      <input type="date" name="event_date" required>
      <label>時間</label>
      <input type="time" name="event_time">
      <label>場所</label>
      <input type="text" name="location" placeholder="例：市営グラウンドA面">
      <label>備考・詳細</label>
      <textarea name="note" placeholder="持ち物・集合場所など"></textarea>
      <button class="btn btn-blue btn-block" type="submit">追加する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/schedule" style="font-size:13px;color:#888">← スケジュールに戻る</a></div>
</div>'''
    return page('予定を追加', body, code, active='schedule')

@app.route('/t/<code>/admin/events/<event_id>')
def admin_event_detail(code, event_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    conn = get_db()
    ev = conn.execute('SELECT * FROM events WHERE id=? AND team_id=?', (event_id, team['id'])).fetchone()
    if not ev:
        conn.close()
        return redirect(url_for('schedule', code=code))
    rsvps = conn.execute('SELECT * FROM rsvps WHERE event_id=? ORDER BY status,member_name', (event_id,)).fetchall()
    members_all = conn.execute('SELECT name FROM members WHERE team_id=? ORDER BY name', (team['id'],)).fetchall()
    conn.close()

    attending = [r for r in rsvps if r['status'] == 'attending']
    absent = [r for r in rsvps if r['status'] == 'absent']
    answered_names = set(r['member_name'] for r in rsvps)
    no_answer = [m['name'] for m in members_all if m['name'] not in answered_names]

    def names(lst):
        return ''.join(f'<div style="font-size:14px;padding:5px 0;border-bottom:1px solid #f0f0f0">{r["member_name"]}</div>' for r in lst) or '<div style="font-size:13px;color:#aaa">なし</div>'

    no_answer_card = ''
    if no_answer:
        no_answer_card = f'''
  <div class="card" style="border-color:#fca5a5">
    <div style="margin-bottom:10px"><span class="badge badge-red">未回答 {len(no_answer)}名</span></div>
    {''.join(f'<div style="font-size:14px;padding:5px 0;border-bottom:1px solid #f0f0f0">{n}</div>' for n in no_answer)}
  </div>'''

    body = f'''
<div class="container">
  <div class="card">
    <h1>{ev['title']}</h1>
    <div style="font-size:14px;color:#555;margin-top:6px">
      📅 {fmt_date(ev['event_date'])}{' ' + ev['event_time'] if ev['event_time'] else ''}
      {('　📍 ' + ev['location']) if ev['location'] else ''}
    </div>
    {f'<div style="margin-top:12px;background:#f8faff;padding:12px;border-radius:10px;font-size:14px">{ev["note"]}</div>' if ev['note'] else ''}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="card">
      <div class="row" style="margin-bottom:10px">
        <span class="badge badge-green">出席 {len(attending)}</span>
      </div>
      {names(attending)}
    </div>
    <div class="card">
      <div class="row" style="margin-bottom:10px">
        <span class="badge badge-red">欠席 {len(absent)}</span>
      </div>
      {names(absent)}
    </div>
  </div>
  {no_answer_card}
  <div style="margin-top:4px">
    <a href="/t/{code}/admin/events/{event_id}/csv" class="btn btn-gray btn-sm">📥 出欠CSVをダウンロード</a>
  </div>
  <div style="text-align:center;margin-top:12px"><a href="/t/{code}/admin/dash" style="font-size:13px;color:#888">← ダッシュボード</a></div>
</div>'''
    return page(ev['title'], body, code, active='admin')


# ── Admin: notices ────────────────────────────────────────────────

@app.route('/t/<code>/admin/notices/new', methods=['GET', 'POST'])
def admin_new_notice(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    error = ''
    prefill_title = request.args.get('title', '')
    prefill_body = request.args.get('body', '')

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body_text = request.form.get('body', '').strip()
        if not title or not body_text:
            error = 'タイトルと本文を入力してください'
        else:
            conn = get_db()
            conn.execute('INSERT INTO notices VALUES (?,?,?,?,?)',
                         (new_id(), team['id'], title, body_text, now_str()))
            conn.commit()
            conn.close()
            return redirect(url_for('notices', code=code, sent='1'))

    conn = get_db()
    team2 = get_team(code)
    templates = conn.execute('SELECT * FROM ai_templates WHERE team_id=? ORDER BY created_at DESC', (team2['id'],)).fetchall() if team2 else []
    conn.close()

    tmpl_opts = ''.join(f'<option value="{t["id"]}" data-title="{t["title"]}" data-body="{t["body"]}">{t["title"]}</option>' for t in templates)
    tmpl_select = f'''
    <div style="margin-bottom:12px">
      <select id="tmpl-select" class="btn btn-sm btn-outline" style="width:auto;border:2px solid #dde6ff;padding:7px 12px" onchange="applyTemplate(this)">
        <option value="">📌 テンプレートから選ぶ</option>
        {tmpl_opts}
      </select>
    </div>
    <script>
    function applyTemplate(sel) {{
      var opt = sel.options[sel.selectedIndex];
      if(opt.value) {{
        document.querySelector('[name=title]').value = opt.dataset.title;
        document.querySelector('[name=body]').value = opt.dataset.body;
      }}
    }}
    </script>''' if templates else ''

    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <h1>お知らせを作成</h1>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
      <a href="/t/{code}/admin/ai?redirect=notice" class="btn btn-sm btn-outline">✦ AIで下書きを作る</a>
    </div>
    {tmpl_select}
    <form method="POST">
      <label>タイトル *</label>
      <input type="text" name="title" placeholder="例：明日の練習について" required value="{prefill_title}">
      <label>本文 *</label>
      <textarea name="body" rows="8" placeholder="メンバーへのお知らせ内容を入力してください" required>{prefill_body}</textarea>
      <button class="btn btn-blue btn-block" type="submit">送信する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/notices" style="font-size:13px;color:#888">← お知らせ一覧</a></div>
</div>'''
    return page('お知らせ作成', body, code, active='notices')


# ── Admin: AI ─────────────────────────────────────────────────────

@app.route('/t/<code>/admin/ai', methods=['GET', 'POST'])
def admin_ai(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))

    redirect_to = request.args.get('redirect', '')
    result_title = ''
    result_body = ''
    error = ''
    memo = ''

    if request.method == 'POST':
        memo = request.form.get('memo', '').strip()
        tone = request.form.get('tone', 'formal')
        if not memo:
            error = 'メモを入力してください'
        elif not ANTHROPIC_API_KEY:
            error = 'ANTHROPIC_API_KEYが設定されていません'
        elif HAS_ANTHROPIC:
            try:
                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                tone_desc = '丁寧でやわらかい' if tone == 'formal' else 'シンプルで簡潔な'
                message = client.messages.create(
                    model='claude-haiku-4-5-20251001',
                    max_tokens=800,
                    messages=[{
                        'role': 'user',
                        'content': f'''あなたはスポーツチームの運営をサポートするAIです。
コーチが書いた短いメモをもとに、保護者・メンバー向けの{tone_desc}連絡文を作成してください。

メモ：{memo}

以下のJSON形式で返してください：
{{"title": "お知らせのタイトル（20字以内）", "body": "本文（200字程度、改行あり）"}}

JSONのみ返してください。説明不要です。'''
                    }]
                )
                import json
                text = message.content[0].text.strip()
                if text.startswith('```'):
                    text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
                data = json.loads(text)
                result_title = data.get('title', '')
                result_body = data.get('body', '')
            except Exception as e:
                error = f'AI生成に失敗しました: {str(e)}'
        else:
            error = 'anthropicライブラリがインストールされていません'

    # テンプレート保存
    saved_msg = ''
    if request.method == 'POST' and request.form.get('action') == 'save_template':
        t_title = request.form.get('t_title', '').strip()
        t_body = request.form.get('t_body', '').strip()
        if t_title and t_body:
            team = get_team(code)
            conn = get_db()
            conn.execute('INSERT INTO ai_templates VALUES (?,?,?,?,?)',
                         (new_id(), team['id'], t_title, t_body, now_str()))
            conn.commit()
            conn.close()
            saved_msg = 'テンプレートに保存しました'
            result_title = t_title
            result_body = t_body

    use_btn = ''
    save_form = ''
    if result_title and result_body:
        import urllib.parse
        params = urllib.parse.urlencode({'title': result_title, 'body': result_body})
        use_btn = f'<a href="/t/{code}/admin/notices/new?{params}" class="btn btn-blue" style="display:block;text-align:center;margin-top:12px">このままお知らせとして送信 →</a>'
        save_form = f'''
        <form method="POST" style="margin-top:8px">
          <input type="hidden" name="action" value="save_template">
          <input type="hidden" name="t_title" value="{result_title}">
          <input type="hidden" name="t_body" value="{result_body}">
          <button class="btn btn-outline btn-sm" type="submit" style="width:100%">📌 テンプレートとして保存</button>
        </form>'''

    # 保存済みテンプレート一覧
    team = get_team(code)
    conn = get_db()
    templates = conn.execute('SELECT * FROM ai_templates WHERE team_id=? ORDER BY created_at DESC', (team['id'],)).fetchall()
    conn.close()

    tmpl_rows = ''
    for t in templates:
        import urllib.parse
        params = urllib.parse.urlencode({'title': t['title'], 'body': t['body']})
        tmpl_rows += f'''
        <div class="card-sm row" style="justify-content:space-between;align-items:center">
          <div style="flex:1;min-width:0">
            <div style="font-weight:700;font-size:14px">{t['title']}</div>
            <div style="font-size:12px;color:#888;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{t['body'][:40]}…</div>
          </div>
          <div style="display:flex;gap:6px;margin-left:12px">
            <a href="/t/{code}/admin/notices/new?{params}" class="btn btn-sm btn-outline">使う</a>
            <a href="/t/{code}/admin/ai/template/{t['id']}/delete" class="btn btn-sm btn-gray">削除</a>
          </div>
        </div>'''

    tmpl_section = f'''
    <div class="card" style="margin-top:16px">
      <h2 style="margin-bottom:12px">📌 保存済みテンプレート</h2>
      {tmpl_rows if templates else '<div class="empty" style="padding:20px">保存されたテンプレートはありません</div>'}
    </div>''' if templates else ''

    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <div class="section-label">✦ AI文章作成</div>
    <h1>AIで下書きを作る</h1>
    <p style="color:#666;font-size:13px;margin-bottom:16px">一言メモを入力するだけで、丁寧な連絡文を自動生成します</p>
    {f'<div class="msg-ok">{saved_msg}</div>' if saved_msg else ''}
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>メモ・キーワード</label>
      <textarea name="memo" placeholder="例：明日の練習、雨で中止&#10;例：5/25試合、集合9時、弁当持参" rows="4">{memo}</textarea>
      <label>文体</label>
      <select name="tone">
        <option value="formal">丁寧・やわらか（保護者向け）</option>
        <option value="simple">シンプル・簡潔（メンバー向け）</option>
      </select>
      <button class="btn btn-blue btn-block" type="submit">✦ AI生成する</button>
    </form>
  </div>

  {('<div class="card" style="border-color:#2563eb"><div class="section-label">生成結果</div><h2>' + result_title + '</h2><div style="white-space:pre-wrap;font-size:14px;color:#333;line-height:1.8;background:#f8faff;padding:14px;border-radius:10px;margin-top:8px">' + result_body + '</div>' + use_btn + save_form + '</div>') if result_title else ''}

  {tmpl_section}

  <div style="text-align:center;margin-top:8px"><a href="/t/{code}/admin/dash" style="font-size:13px;color:#888">← ダッシュボード</a></div>
</div>'''
    return page('AI文章作成', body, code, active='ai')


@app.route('/t/<code>/admin/ai/template/<tmpl_id>/delete')
def admin_delete_template(code, tmpl_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    conn = get_db()
    conn.execute('DELETE FROM ai_templates WHERE id=? AND team_id=?', (tmpl_id, team['id']))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_ai', code=code))


# ── Admin: members ───────────────────────────────────────────────

@app.route('/t/<code>/admin/members', methods=['GET', 'POST'])
def admin_members(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    msg = ''

    if request.method == 'POST':
        action = request.form.get('action')
        conn = get_db()
        if action == 'add':
            name = request.form.get('name', '').strip()
            number = request.form.get('number', '').strip()
            position = request.form.get('position', '').strip()
            if name:
                conn.execute('INSERT INTO members VALUES (?,?,?,?,?,?)',
                             (new_id(), team['id'], name, number, position, now_str()))
                conn.commit()
                msg = f'「{name}」を追加しました'
        elif action == 'delete':
            mid = request.form.get('member_id')
            conn.execute('DELETE FROM members WHERE id=? AND team_id=?', (mid, team['id']))
            conn.commit()
            msg = 'メンバーを削除しました'
        conn.close()

    conn = get_db()
    members = conn.execute('SELECT * FROM members WHERE team_id=? ORDER BY joined_at', (team['id'],)).fetchall()
    conn.close()

    rows = ''
    for m in members:
        rows += f'''
        <div class="card-sm">
          <div class="row" style="justify-content:space-between;align-items:center">
            <div>
              <span style="font-weight:700">{m['name']}</span>
              {f'<span style="font-size:12px;color:#888;margin-left:8px">#{m["number"]}</span>' if m['number'] else ''}
              {f'<span style="font-size:12px;color:#888;margin-left:6px">{m["position"]}</span>' if m['position'] else ''}
            </div>
            <div style="display:flex;gap:6px">
              <a href="/t/{code}/admin/members/{m['id']}/edit" class="btn btn-sm btn-outline">編集</a>
              <form method="POST" onsubmit="return confirm('{m['name']}を削除しますか？')" style="margin:0">
                <input type="hidden" name="action" value="delete">
                <input type="hidden" name="member_id" value="{m['id']}">
                <button class="btn btn-sm btn-gray" type="submit">削除</button>
              </form>
            </div>
          </div>
        </div>'''

    body = f'''
<div class="container" style="max-width:540px">
  {f'<div class="msg-ok">{msg}</div>' if msg else ''}
  <div class="card">
    <div class="row" style="margin-bottom:16px">
      <h1 style="margin:0">👥 メンバー名簿</h1>
      <span class="badge badge-blue" style="margin-left:auto">{len(members)}名</span>
    </div>
    {rows if members else '<div class="empty">まだメンバーがいません</div>'}
  </div>
  <div class="card">
    <h2>メンバーを追加</h2>
    <form method="POST">
      <input type="hidden" name="action" value="add">
      <label>名前 *</label>
      <input type="text" name="name" placeholder="例：田中 花子" required>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <label>背番号</label>
          <input type="text" name="number" placeholder="例：10">
        </div>
        <div>
          <label>ポジション</label>
          <input type="text" name="position" placeholder="例：FW">
        </div>
      </div>
      <button class="btn btn-blue btn-block" type="submit">追加する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/admin/dash" style="font-size:13px;color:#888">← ダッシュボード</a></div>
</div>'''
    return page('メンバー管理', body, code, active='admin')


@app.route('/t/<code>/admin/members/<member_id>/edit', methods=['GET', 'POST'])
def admin_edit_member(code, member_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    conn = get_db()
    m = conn.execute('SELECT * FROM members WHERE id=? AND team_id=?', (member_id, team['id'])).fetchone()
    if not m:
        conn.close()
        return redirect(url_for('admin_members', code=code))

    msg = ''
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        number = request.form.get('number', '').strip()
        position = request.form.get('position', '').strip()
        if name:
            conn.execute('UPDATE members SET name=?, number=?, position=? WHERE id=?',
                         (name, number, position, member_id))
            conn.commit()
            conn.close()
            return redirect(url_for('admin_members', code=code))

    conn.close()
    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>メンバーを編集</h1>
    <form method="POST">
      <label>名前 *</label>
      <input type="text" name="name" value="{m['name']}" required>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <label>背番号</label>
          <input type="text" name="number" value="{m['number']}">
        </div>
        <div>
          <label>ポジション</label>
          <input type="text" name="position" value="{m['position']}">
        </div>
      </div>
      <button class="btn btn-blue btn-block" type="submit">保存する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/admin/members" style="font-size:13px;color:#888">← メンバー一覧</a></div>
</div>'''
    return page('メンバー編集', body, code, active='admin')


# ── Members (all users view) ──────────────────────────────────────

@app.route('/t/<code>/members')
def member_list(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    members = conn.execute('SELECT * FROM members WHERE team_id=? ORDER BY CAST(number AS INTEGER), name', (team['id'],)).fetchall()
    conn.close()

    rows = ''
    for m in members:
        rows += f'''
        <div class="card-sm row" style="align-items:center;gap:14px">
          <div style="width:32px;height:32px;border-radius:50%;background:#eff6ff;color:#2563eb;font-weight:900;font-size:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0">
            {m['number'] if m['number'] else '—'}
          </div>
          <div>
            <div style="font-weight:700">{m['name']}</div>
            {f'<div style="font-size:12px;color:#888">{m["position"]}</div>' if m['position'] else ''}
          </div>
        </div>'''

    edit_btn = f'<a href="/t/{code}/admin/members" class="btn btn-sm btn-outline">編集</a>' if admin else ''
    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <div class="row" style="margin-bottom:16px">
      <div>
        <span class="section-label">👥 メンバー</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-left:auto">
        <span class="badge badge-blue">{len(members)}名</span>
        {edit_btn}
      </div>
    </div>
    {rows if members else '<div class="empty">まだメンバーがいません</div>'}
  </div>
</div>'''
    return page('メンバー', body, code, active='members')


# ── Fees (member view) ────────────────────────────────────────────

@app.route('/t/<code>/fees')
def member_fees(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    fees = conn.execute('SELECT * FROM fees WHERE team_id=? ORDER BY due_date,created_at', (team['id'],)).fetchall()

    cards = ''
    for f in fees:
        if member:
            paid_row = conn.execute('SELECT paid FROM fee_payments WHERE fee_id=? AND member_name=?',
                                    (f['id'], member)).fetchone()
            paid = paid_row['paid'] if paid_row else 0
            badge = '<span class="badge badge-green">支払済</span>' if paid else '<span class="badge badge-red">未払い</span>'
        else:
            total = conn.execute('SELECT COUNT(*) FROM fee_payments WHERE fee_id=?', (f['id'],)).fetchone()[0]
            paid_count = conn.execute('SELECT COUNT(*) FROM fee_payments WHERE fee_id=? AND paid=1', (f['id'],)).fetchone()[0]
            badge = f'<span class="badge badge-blue">支払済 {paid_count}/{total}</span>'

        cards += f'''
        <div class="card-sm">
          <div class="row" style="justify-content:space-between;align-items:center">
            <div>
              <div style="font-weight:700">{f['title']}</div>
              <div style="font-size:13px;color:#555;margin-top:2px">
                ¥{f['amount']:,}{'　期限：' + fmt_date(f['due_date']) if f['due_date'] else ''}
              </div>
              {f'<div style="font-size:12px;color:#888;margin-top:4px">{f["note"]}</div>' if f['note'] else ''}
            </div>
            {badge}
          </div>
        </div>'''
    conn.close()

    new_btn = f'<a href="/t/{code}/admin/fees/new" class="btn btn-blue btn-sm">＋ 集金項目を追加</a>' if admin else ''
    body = f'''
<div class="container">
  <div class="row" style="margin-bottom:16px">
    <div><span class="section-label">💰 集金</span></div>
    {new_btn}
  </div>
  {cards if fees else '<div class="empty card">📭<br>集金項目はまだありません</div>'}
</div>'''
    return page('集金', body, code, active='fees')


# ── Admin: fees ───────────────────────────────────────────────────

@app.route('/t/<code>/admin/fees')
def admin_fees(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    conn = get_db()
    fees = conn.execute('SELECT * FROM fees WHERE team_id=? ORDER BY due_date,created_at', (team['id'],)).fetchall()

    rows = ''
    for f in fees:
        paid_count = conn.execute('SELECT COUNT(*) FROM fee_payments WHERE fee_id=? AND paid=1', (f['id'],)).fetchone()[0]
        total = conn.execute('SELECT COUNT(*) FROM fee_payments WHERE fee_id=?', (f['id'],)).fetchone()[0]
        rows += f'''
        <div class="card-sm row" style="justify-content:space-between;align-items:center">
          <div>
            <div style="font-weight:700">{f['title']}</div>
            <div style="font-size:12px;color:#888">¥{f['amount']:,}{'　期限：' + fmt_date(f['due_date']) if f['due_date'] else ''}　支払済 {paid_count}/{total}名</div>
          </div>
          <a href="/t/{code}/admin/fees/{f['id']}" class="btn btn-sm btn-outline">管理</a>
        </div>'''
    conn.close()

    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <div class="row" style="margin-bottom:16px">
      <h1 style="margin:0">💰 集金管理</h1>
      <a href="/t/{code}/admin/fees/new" class="btn btn-sm btn-blue" style="margin-left:auto">＋ 追加</a>
    </div>
    {rows if fees else '<div class="empty">集金項目がありません</div>'}
  </div>
  <div style="text-align:center"><a href="/t/{code}/admin/dash" style="font-size:13px;color:#888">← ダッシュボード</a></div>
</div>'''
    return page('集金管理', body, code, active='admin')


@app.route('/t/<code>/admin/fees/new', methods=['GET', 'POST'])
def admin_new_fee(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    error = ''

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        amount = request.form.get('amount', '0').strip().replace(',', '')
        due_date = request.form.get('due_date', '').strip()
        note = request.form.get('note', '').strip()
        if not title:
            error = 'タイトルを入力してください'
        else:
            conn = get_db()
            fee_id = new_id()
            conn.execute('INSERT INTO fees VALUES (?,?,?,?,?,?,?)',
                         (fee_id, team['id'], title, int(amount or 0), due_date, note, now_str()))
            members = conn.execute('SELECT name FROM members WHERE team_id=?', (team['id'],)).fetchall()
            for m in members:
                conn.execute('INSERT OR IGNORE INTO fee_payments VALUES (?,?,?,0,?)',
                             (new_id(), fee_id, m['name'], ''))
            conn.commit()
            conn.close()
            return redirect(url_for('admin_fee_detail', code=code, fee_id=fee_id))

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>集金項目を追加</h1>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>タイトル *</label>
      <input type="text" name="title" placeholder="例：月会費5月分、合宿費" required>
      <label>金額（円）</label>
      <input type="text" name="amount" placeholder="例：3000">
      <label>支払い期限</label>
      <input type="date" name="due_date">
      <label>備考</label>
      <textarea name="note" placeholder="振込先など" rows="3"></textarea>
      <button class="btn btn-blue btn-block" type="submit">作成する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/admin/fees" style="font-size:13px;color:#888">← 集金一覧</a></div>
</div>'''
    return page('集金項目を追加', body, code, active='admin')


@app.route('/t/<code>/admin/fees/<fee_id>', methods=['GET', 'POST'])
def admin_fee_detail(code, fee_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    conn = get_db()
    f = conn.execute('SELECT * FROM fees WHERE id=? AND team_id=?', (fee_id, team['id'])).fetchone()
    if not f:
        conn.close()
        return redirect(url_for('admin_fees', code=code))

    if request.method == 'POST':
        member_name = request.form.get('member_name')
        paid = int(request.form.get('paid', 0))
        paid_at = now_str() if paid else ''
        conn.execute('''
            INSERT INTO fee_payments (id,fee_id,member_name,paid,paid_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(fee_id,member_name) DO UPDATE SET paid=excluded.paid, paid_at=excluded.paid_at
        ''', (new_id(), fee_id, member_name, paid, paid_at))
        conn.commit()

    members = conn.execute('SELECT * FROM members WHERE team_id=? ORDER BY name', (team['id'],)).fetchall()
    payments = conn.execute('SELECT * FROM fee_payments WHERE fee_id=?', (fee_id,)).fetchall()
    pay_map = {p['member_name']: p for p in payments}
    conn.close()

    rows = ''
    for m in members:
        p = pay_map.get(m['name'])
        paid = p['paid'] if p else 0
        paid_at = p['paid_at'] if p else ''
        toggle_val = 0 if paid else 1
        btn_class = 'btn-green' if paid else 'btn-gray'
        btn_label = '✅ 支払済' if paid else '未払い'
        rows += f'''
        <div class="card-sm row" style="justify-content:space-between;align-items:center">
          <div>
            <span style="font-weight:700">{m['name']}</span>
            {f'<span style="font-size:11px;color:#aaa;margin-left:8px">{paid_at}</span>' if paid_at else ''}
          </div>
          <form method="POST">
            <input type="hidden" name="member_name" value="{m['name']}">
            <input type="hidden" name="paid" value="{toggle_val}">
            <button class="btn btn-sm {'btn-blue' if paid else 'btn-outline'}" type="submit">{btn_label}</button>
          </form>
        </div>'''

    paid_count = sum(1 for m in members if pay_map.get(m['name']) and pay_map[m['name']]['paid'])

    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <h1>{f['title']}</h1>
    <div style="font-size:14px;color:#555;margin-top:4px">
      ¥{f['amount']:,}{'　期限：' + fmt_date(f['due_date']) if f['due_date'] else ''}
    </div>
    {f'<div style="font-size:13px;color:#666;margin-top:8px">{f["note"]}</div>' if f['note'] else ''}
    <div style="margin-top:12px;display:flex;gap:10px">
      <span class="badge badge-green">支払済 {paid_count}名</span>
      <span class="badge badge-red">未払い {len(members)-paid_count}名</span>
    </div>
  </div>
  <div class="card">
    <h2 style="margin-bottom:12px">支払い状況</h2>
    {rows if members else '<div class="empty">メンバーがいません。先にメンバー名簿を登録してください。</div>'}
  </div>
  <div style="text-align:center"><a href="/t/{code}/admin/fees" style="font-size:13px;color:#888">← 集金一覧</a></div>
</div>'''
    return page(f['title'], body, code, active='admin')


# ── Admin: CSV export ─────────────────────────────────────────────

@app.route('/t/<code>/admin/events/<event_id>/csv')
def admin_event_csv(code, event_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    conn = get_db()
    ev = conn.execute('SELECT * FROM events WHERE id=? AND team_id=?', (event_id, team['id'])).fetchone()
    if not ev:
        conn.close()
        return redirect(url_for('schedule', code=code))

    members = conn.execute('SELECT * FROM members WHERE team_id=? ORDER BY name', (team['id'],)).fetchall()
    rsvps = conn.execute('SELECT * FROM rsvps WHERE event_id=?', (event_id,)).fetchall()
    conn.close()

    rsvp_map = {r['member_name']: r['status'] for r in rsvps}
    status_label = {'attending': '出席', 'absent': '欠席'}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['名前', '背番号', 'ポジション', '出欠', '更新日時'])

    if members:
        for m in members:
            status = rsvp_map.get(m['name'], '未回答')
            writer.writerow([m['name'], m['number'], m['position'],
                             status_label.get(status, status),
                             next((r['updated_at'] for r in rsvps if r['member_name'] == m['name']), '')])
    else:
        for name, status in rsvp_map.items():
            writer.writerow([name, '', '', status_label.get(status, status),
                             next((r['updated_at'] for r in rsvps if r['member_name'] == name), '')])

    filename = f"出欠_{ev['title']}_{ev['event_date']}.csv"
    return csv_response(output.getvalue(), filename)


# ── Order Forms ──────────────────────────────────────────────────

@app.route('/t/<code>/orders')
def orders_list(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    forms = conn.execute(
        'SELECT * FROM order_forms WHERE team_id=? ORDER BY created_at DESC',
        (team['id'],)
    ).fetchall()

    cards = ''
    for f in forms:
        field_count = conn.execute('SELECT COUNT(*) FROM order_form_fields WHERE form_id=?', (f['id'],)).fetchone()[0]
        response_count = conn.execute('SELECT COUNT(*) FROM order_responses WHERE form_id=?', (f['id'],)).fetchone()[0]
        has_responded = bool(conn.execute(
            'SELECT 1 FROM order_responses WHERE form_id=? AND member_name=?', (f['id'], member)
        ).fetchone()) if member else False

        if admin:
            badge = f'<span class="badge badge-blue">{response_count}件の回答</span>'
        elif has_responded:
            badge = '<span class="badge badge-green">回答済</span>'
        else:
            badge = '<span class="badge badge-red">未回答</span>'

        deadline_html = f'　期限：{fmt_date(f["deadline"])}' if f['deadline'] else ''
        cards += f'''
        <a href="/t/{code}/orders/{f['id']}" style="text-decoration:none;display:block">
          <div class="card-sm">
            <div class="row" style="justify-content:space-between">
              <div>
                <div style="font-weight:700;color:#1a1a1a">{f['title']}</div>
                <div style="font-size:12px;color:#aaa;margin-top:4px">{fmt_datetime(f['created_at'])}{deadline_html}　項目 {field_count}件</div>
              </div>
              {badge}
            </div>
          </div>
        </a>'''
    conn.close()

    new_btn = f'<a href="/t/{code}/admin/orders/new" class="btn btn-blue btn-sm">＋ フォーム作成</a>' if admin else ''
    body = f'''
<div class="container">
  <div class="row" style="margin-bottom:16px">
    <div><span class="section-label">📋 注文フォーム</span></div>
    {new_btn}
  </div>
  {cards if forms else '<div class="empty card">📭<br>注文フォームはまだありません</div>'}
</div>'''
    return page('注文フォーム', body, code, active='orders')


@app.route('/t/<code>/orders/<form_id>', methods=['GET', 'POST'])
def order_form_view(code, form_id):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    form = conn.execute(
        'SELECT * FROM order_forms WHERE id=? AND team_id=?', (form_id, team['id'])
    ).fetchone()
    if not form:
        conn.close()
        return redirect(url_for('orders_list', code=code))

    fields = conn.execute(
        'SELECT * FROM order_form_fields WHERE form_id=? ORDER BY sort_order', (form_id,)
    ).fetchall()

    photos = conn.execute(
        'SELECT * FROM order_form_photos WHERE form_id=? ORDER BY uploaded_at', (form_id,)
    ).fetchall()

    if not admin and request.method == 'POST' and member:
        resp = conn.execute(
            'SELECT id FROM order_responses WHERE form_id=? AND member_name=?', (form_id, member)
        ).fetchone()
        if resp:
            resp_id = resp['id']
            conn.execute('UPDATE order_responses SET submitted_at=? WHERE id=?', (now_str(), resp_id))
            conn.execute('DELETE FROM order_response_values WHERE response_id=?', (resp_id,))
        else:
            resp_id = new_id()
            conn.execute('INSERT INTO order_responses VALUES (?,?,?,?)',
                         (resp_id, form_id, member, now_str()))
        for field in fields:
            value = request.form.get(f'field_{field["id"]}', '').strip()
            conn.execute('INSERT INTO order_response_values VALUES (?,?,?,?)',
                         (new_id(), resp_id, field['id'], value))
        conn.commit()
        conn.close()
        return redirect(url_for('orders_list', code=code))

    if admin:
        responses = conn.execute(
            'SELECT * FROM order_responses WHERE form_id=? ORDER BY submitted_at', (form_id,)
        ).fetchall()

        resp_rows = ''
        for r in responses:
            vals = conn.execute(
                'SELECT * FROM order_response_values WHERE response_id=?', (r['id'],)
            ).fetchall()
            val_map = {v['field_id']: v['value'] for v in vals}
            cells = ''.join(
                f'<td style="padding:8px 12px;border-bottom:1px solid #e0e8ff">{val_map.get(f["id"], "")}</td>'
                for f in fields
            )
            resp_rows += (
                f'<tr><td style="padding:8px 12px;border-bottom:1px solid #e0e8ff;font-weight:700">{r["member_name"]}</td>'
                f'{cells}'
                f'<td style="padding:8px 12px;border-bottom:1px solid #e0e8ff;font-size:12px;color:#aaa">{fmt_datetime(r["submitted_at"])}</td></tr>'
            )

        headers = ''.join(
            f'<th style="padding:8px 12px;text-align:left;font-size:13px;color:#2563eb">{f["label"]}</th>'
            for f in fields
        )

        field_rows = ''
        for f in fields:
            f_opts = f'（{f["options"]}）' if f['options'] else ''
            f_type_label = '選択' if f['field_type'] == 'select' else 'テキスト'
            field_rows += f'''
            <div class="card-sm row" style="justify-content:space-between;align-items:center">
              <div>
                <span style="font-weight:700">{f["label"]}</span>
                <span style="font-size:12px;color:#888;margin-left:8px">{f_type_label}{f_opts}</span>
              </div>
              <a href="/t/{code}/admin/orders/{form_id}/field/{f['id']}/delete"
                 class="btn btn-sm btn-gray"
                 onclick="return confirm('削除しますか？')">削除</a>
            </div>'''

        conn.close()

        deadline_html = f'<div style="font-size:13px;color:#f59e0b">期限：{fmt_date(form["deadline"])}</div>' if form['deadline'] else ''
        desc_html = f'<div style="font-size:13px;color:#666;margin-bottom:8px">{form["description"]}</div>' if form['description'] else ''

        photo_thumbs = ''.join(
            f'<div style="position:relative;display:inline-block">'
            f'<img src="/uploads/{p["id"]}" style="width:120px;height:90px;object-fit:cover;border-radius:10px;border:1.5px solid #e0e8ff">'
            f'<a href="/t/{code}/admin/orders/{form_id}/photo/{p["id"]}/delete"'
            f' style="position:absolute;top:-7px;right:-7px;background:#ef4444;color:#fff;border-radius:50%;width:22px;height:22px;font-size:13px;font-weight:900;display:flex;align-items:center;justify-content:center;text-decoration:none"'
            f' onclick="return confirm(\'削除しますか？\')">×</a>'
            f'</div>'
            for p in photos
        )
        photo_grid = f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px">{photo_thumbs}</div>' if photos else '<div class="empty" style="padding:12px">まだ写真がありません</div>'
        photo_card = f'''
  <div class="card">
    <h2 style="margin-bottom:12px">📸 写真（メンバーにも表示されます）</h2>
    {photo_grid}
    <form method="POST" action="/t/{code}/admin/orders/{form_id}/photo" enctype="multipart/form-data">
      <label>写真を追加（複数選択可・JPG/PNG/GIF/WebP）</label>
      <input type="file" name="photos" accept="image/*" multiple style="padding:8px;background:#fafcff">
      <button class="btn btn-outline btn-sm" type="submit" style="margin-top:8px">📤 アップロード</button>
    </form>
  </div>'''

        if responses:
            table_html = (
                f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse">'
                f'<thead><tr>'
                f'<th style="padding:8px 12px;text-align:left;font-size:13px;color:#2563eb">名前</th>'
                f'{headers}'
                f'<th style="padding:8px 12px;text-align:left;font-size:13px;color:#2563eb">回答日時</th>'
                f'</tr></thead><tbody>{resp_rows}</tbody></table></div>'
            )
        else:
            table_html = '<div class="empty">まだ回答がありません</div>'

        body = f'''
<div class="container" style="max-width:680px">
  <div class="card">
    <div style="font-weight:700;font-size:20px;margin-bottom:4px">{form["title"]}</div>
    {desc_html}
    {deadline_html}
    <div style="margin-top:12px">
      <a href="/t/{code}/admin/orders/{form_id}/csv" class="btn btn-gray btn-sm">📥 CSVダウンロード</a>
    </div>
  </div>

  {photo_card}

  <div class="card">
    <div class="row" style="margin-bottom:12px">
      <h2 style="margin:0">回答一覧 <span class="badge badge-blue" style="font-size:13px">{len(responses)}件</span></h2>
    </div>
    {table_html}
  </div>

  <div class="card">
    <h2 style="margin-bottom:12px">項目管理</h2>
    {field_rows if fields else '<div class="empty" style="padding:16px">まだ項目がありません</div>'}
    <form method="POST" action="/t/{code}/admin/orders/{form_id}/field" style="margin-top:16px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div>
          <label>項目名 *</label>
          <input type="text" name="label" placeholder="例：お弁当の種類" required>
        </div>
        <div>
          <label>種類</label>
          <select name="field_type" id="ftype" onchange="toggleOpts()">
            <option value="text">テキスト入力</option>
            <option value="select">選択肢から選ぶ</option>
          </select>
        </div>
      </div>
      <div id="opts-area" style="display:none;margin-top:10px">
        <label>選択肢（カンマ区切り）</label>
        <input type="text" name="options" placeholder="例：のり弁,唐揚げ弁当,幕の内">
      </div>
      <button class="btn btn-outline btn-block" type="submit" style="margin-top:12px">＋ 項目を追加</button>
    </form>
  </div>

  <div style="text-align:center"><a href="/t/{code}/orders" style="font-size:13px;color:#888">← フォーム一覧</a></div>
</div>
<script>
function toggleOpts() {{
  document.getElementById('opts-area').style.display =
    document.getElementById('ftype').value === 'select' ? 'block' : 'none';
}}
</script>'''
        return page(form['title'], body, code, active='orders')

    # Member: fill form
    my_resp = conn.execute(
        'SELECT * FROM order_responses WHERE form_id=? AND member_name=?', (form_id, member)
    ).fetchone()
    my_values = {}
    if my_resp:
        vals = conn.execute(
            'SELECT * FROM order_response_values WHERE response_id=?', (my_resp['id'],)
        ).fetchall()
        my_values = {v['field_id']: v['value'] for v in vals}

    conn.close()

    field_inputs = ''
    for field in fields:
        current_val = my_values.get(field['id'], '')
        if field['field_type'] == 'select' and field['options']:
            opts_list = [o.strip() for o in field['options'].split(',') if o.strip()]
            options_html = '<option value="">選択してください</option>'
            options_html += ''.join(
                f'<option value="{o}" {"selected" if current_val == o else ""}>{o}</option>'
                for o in opts_list
            )
            field_inputs += f'<label>{field["label"]}</label><select name="field_{field["id"]}">{options_html}</select>'
        else:
            field_inputs += (
                f'<label>{field["label"]}</label>'
                f'<input type="text" name="field_{field["id"]}" value="{current_val}" placeholder="入力してください">'
            )

    submit_label = '更新する' if my_resp else '送信する'
    deadline_html = f'<div style="font-size:13px;color:#f59e0b;margin-bottom:12px">期限：{fmt_date(form["deadline"])}</div>' if form['deadline'] else ''
    desc_html = f'<div style="font-size:13px;color:#666;margin-bottom:12px">{form["description"]}</div>' if form['description'] else ''
    already_html = '<div class="msg-ok">✅ 回答済みです。修正して再送信できます。</div>' if my_resp else ''
    photos_html = ''.join(
        f'<img src="/uploads/{p["id"]}" style="width:100%;border-radius:10px;border:1.5px solid #e0e8ff;margin-bottom:10px;display:block">'
        for p in photos
    )

    no_fields_html = '<div class="empty" style="padding:20px">まだ項目が設定されていません</div>' if not fields else ''

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <div style="font-weight:700;font-size:20px;margin-bottom:8px">{form["title"]}</div>
    {desc_html}
    {deadline_html}
    {photos_html}
    {already_html}
    {no_fields_html}
    {'<form method="POST">' + field_inputs + f'<button class="btn btn-blue btn-block" type="submit">{submit_label}</button></form>' if fields else ''}
  </div>
  <div style="text-align:center"><a href="/t/{code}/orders" style="font-size:13px;color:#888">← 一覧に戻る</a></div>
</div>'''
    return page(form['title'], body, code, active='orders')


@app.route('/t/<code>/admin/orders/new', methods=['GET', 'POST'])
def admin_new_order_form(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    error = ''

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        deadline = request.form.get('deadline', '').strip()
        if not title:
            error = 'フォーム名を入力してください'
        else:
            conn = get_db()
            form_id = new_id()
            conn.execute('INSERT INTO order_forms VALUES (?,?,?,?,?,?)',
                         (form_id, team['id'], title, description, deadline, now_str()))
            conn.commit()
            conn.close()
            return redirect(url_for('order_form_view', code=code, form_id=form_id))

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>注文フォームを作成</h1>
    <p style="color:#666;font-size:13px;margin-bottom:16px">フォームを作成後、項目（質問）を追加できます</p>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>フォーム名 *</label>
      <input type="text" name="title" placeholder="例：遠征弁当注文、ユニフォームサイズ確認" required>
      <label>説明（任意）</label>
      <textarea name="description" placeholder="例：5/25（日）遠征分のお弁当を注文してください" rows="3"></textarea>
      <label>回答期限（任意）</label>
      <input type="date" name="deadline">
      <button class="btn btn-blue btn-block" type="submit">作成する →</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/orders" style="font-size:13px;color:#888">← フォーム一覧</a></div>
</div>'''
    return page('フォーム作成', body, code, active='orders')


@app.route('/uploads/<photo_id>')
def serve_photo(photo_id):
    if not photo_id.replace('-', '').isalnum():
        return 'Not found', 404
    conn = get_db()
    photo = conn.execute('SELECT * FROM order_form_photos WHERE id=?', (photo_id,)).fetchone()
    conn.close()
    if not photo:
        return 'Not found', 404
    path = os.path.join(UPLOAD_DIR, photo_id)
    if not os.path.exists(path):
        return 'Not found', 404
    return send_file(path, mimetype=photo['mime_type'])


@app.route('/t/<code>/admin/orders/<form_id>/photo', methods=['POST'])
def admin_upload_order_photo(code, form_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    conn = get_db()
    form = conn.execute(
        'SELECT * FROM order_forms WHERE id=? AND team_id=?', (form_id, team['id'])
    ).fetchone()
    if not form:
        conn.close()
        return redirect(url_for('orders_list', code=code))

    allowed = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    for f in request.files.getlist('photos'):
        if f and f.mimetype in allowed:
            photo_id = new_id()
            f.save(os.path.join(UPLOAD_DIR, photo_id))
            conn.execute('INSERT INTO order_form_photos VALUES (?,?,?,?,?)',
                         (photo_id, form_id, f.filename or '', f.mimetype, now_str()))
    conn.commit()
    conn.close()
    return redirect(url_for('order_form_view', code=code, form_id=form_id))


@app.route('/t/<code>/admin/orders/<form_id>/photo/<photo_id>/delete')
def admin_delete_order_photo(code, form_id, photo_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    conn = get_db()
    photo = conn.execute(
        'SELECT * FROM order_form_photos WHERE id=? AND form_id=?', (photo_id, form_id)
    ).fetchone()
    if photo:
        path = os.path.join(UPLOAD_DIR, photo_id)
        if os.path.exists(path):
            os.remove(path)
        conn.execute('DELETE FROM order_form_photos WHERE id=?', (photo_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('order_form_view', code=code, form_id=form_id))


@app.route('/t/<code>/admin/orders/<form_id>/field', methods=['POST'])
def admin_add_order_field(code, form_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    conn = get_db()
    form = conn.execute(
        'SELECT * FROM order_forms WHERE id=? AND team_id=?', (form_id, team['id'])
    ).fetchone()
    if not form:
        conn.close()
        return redirect(url_for('orders_list', code=code))
    label = request.form.get('label', '').strip()
    field_type = request.form.get('field_type', 'text')
    options = request.form.get('options', '').strip()
    if label:
        sort_order = conn.execute(
            'SELECT COUNT(*) FROM order_form_fields WHERE form_id=?', (form_id,)
        ).fetchone()[0]
        conn.execute('INSERT INTO order_form_fields VALUES (?,?,?,?,?,?)',
                     (new_id(), form_id, label, field_type, options, sort_order))
        conn.commit()
    conn.close()
    return redirect(url_for('order_form_view', code=code, form_id=form_id))


@app.route('/t/<code>/admin/orders/<form_id>/field/<field_id>/delete')
def admin_delete_order_field(code, form_id, field_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    conn = get_db()
    conn.execute('DELETE FROM order_form_fields WHERE id=? AND form_id=?', (field_id, form_id))
    conn.commit()
    conn.close()
    return redirect(url_for('order_form_view', code=code, form_id=form_id))


@app.route('/t/<code>/admin/orders/<form_id>/csv')
def admin_order_form_csv(code, form_id):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    conn = get_db()
    form = conn.execute(
        'SELECT * FROM order_forms WHERE id=? AND team_id=?', (form_id, team['id'])
    ).fetchone()
    if not form:
        conn.close()
        return redirect(url_for('orders_list', code=code))
    fields = conn.execute(
        'SELECT * FROM order_form_fields WHERE form_id=? ORDER BY sort_order', (form_id,)
    ).fetchall()
    responses = conn.execute(
        'SELECT * FROM order_responses WHERE form_id=? ORDER BY submitted_at', (form_id,)
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['名前', '回答日時'] + [f['label'] for f in fields])
    for r in responses:
        vals = conn.execute(
            'SELECT * FROM order_response_values WHERE response_id=?', (r['id'],)
        ).fetchall()
        val_map = {v['field_id']: v['value'] for v in vals}
        writer.writerow([r['member_name'], r['submitted_at']] + [val_map.get(f['id'], '') for f in fields])
    conn.close()

    filename = f"注文_{form['title']}_{now_str()[:10]}.csv"
    return csv_response(output.getvalue(), filename)


# ── Survey ───────────────────────────────────────────────────────

@app.route('/t/<code>/survey')
def survey_list(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    surveys = conn.execute('SELECT * FROM surveys WHERE team_id=? ORDER BY created_at DESC', (team['id'],)).fetchall()

    cards = ''
    for sv in surveys:
        options = conn.execute('SELECT * FROM survey_options WHERE survey_id=? ORDER BY sort_order', (sv['id'],)).fetchall()
        total = conn.execute('SELECT COUNT(*) FROM survey_answers WHERE survey_id=?', (sv['id'],)).fetchone()[0]
        answered = bool(conn.execute('SELECT 1 FROM survey_answers WHERE survey_id=? AND member_name=?', (sv['id'], member)).fetchone()) if member else True

        cards += f'''
        <a href="/t/{code}/survey/{sv['id']}" style="text-decoration:none;display:block">
          <div class="card-sm">
            <div class="row" style="justify-content:space-between">
              <div style="font-weight:700;color:#1a1a1a">{'📌 ' if not answered else ''}{sv['title']}</div>
              {'<span class="badge badge-red">未回答</span>' if not answered else f'<span class="badge badge-gray">回答済 {total}名</span>'}
            </div>
            <div style="font-size:12px;color:#aaa;margin-top:4px">{fmt_datetime(sv['created_at'])}　選択肢 {len(options)}件</div>
          </div>
        </a>'''
    conn.close()

    new_btn = f'<a href="/t/{code}/admin/survey/new" class="btn btn-blue btn-sm">＋ 作成</a>' if admin else ''
    body = f'''
<div class="container">
  <div class="row" style="margin-bottom:16px">
    <div><span class="section-label">📊 アンケート</span></div>
    {new_btn}
  </div>
  {cards if surveys else '<div class="empty card">📭<br>アンケートはまだありません</div>'}
</div>'''
    return page('アンケート', body, code, active='survey')


@app.route('/t/<code>/survey/<survey_id>', methods=['GET', 'POST'])
def survey_detail(code, survey_id):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    sv = conn.execute('SELECT * FROM surveys WHERE id=? AND team_id=?', (survey_id, team['id'])).fetchone()
    if not sv:
        conn.close()
        return redirect(url_for('survey_list', code=code))

    options = conn.execute('SELECT * FROM survey_options WHERE survey_id=? ORDER BY sort_order', (survey_id,)).fetchall()

    if request.method == 'POST' and member:
        option_id = request.form.get('option_id')
        if option_id:
            conn.execute('''
                INSERT INTO survey_answers (id,survey_id,option_id,member_name,answered_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(survey_id,member_name) DO UPDATE SET option_id=excluded.option_id, answered_at=excluded.answered_at
            ''', (new_id(), survey_id, option_id, member, now_str()))
            conn.commit()

    my_answer = conn.execute('SELECT option_id FROM survey_answers WHERE survey_id=? AND member_name=?', (survey_id, member)).fetchone() if member else None
    my_option_id = my_answer['option_id'] if my_answer else None

    results = {}
    for opt in options:
        count = conn.execute('SELECT COUNT(*) FROM survey_answers WHERE survey_id=? AND option_id=?', (survey_id, opt['id'])).fetchone()[0]
        results[opt['id']] = count
    total = sum(results.values())

    option_btns = ''
    for opt in options:
        selected = my_option_id == opt['id']
        count = results[opt['id']]
        pct = int(count / total * 100) if total > 0 else 0
        if member:
            option_btns += f'''
            <form method="POST" style="margin-bottom:8px">
              <input type="hidden" name="option_id" value="{opt['id']}">
              <button type="submit" class="btn {'btn-blue' if selected else 'btn-outline'}" style="width:100%;text-align:left;padding:12px 16px">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span>{'✓ ' if selected else ''}{opt['label']}</span>
                  <span style="font-size:13px;opacity:.8">{count}票 ({pct}%)</span>
                </div>
                <div style="margin-top:6px;height:4px;border-radius:4px;background:{'rgba(255,255,255,.3)' if selected else '#e0e8ff'}">
                  <div style="height:4px;border-radius:4px;background:{'rgba(255,255,255,.8)' if selected else '#2563eb'};width:{pct}%"></div>
                </div>
              </button>
            </form>'''
        else:
            option_btns += f'''
            <div style="margin-bottom:8px;padding:12px 16px;border:1.5px solid #e0e8ff;border-radius:10px;background:#fff">
              <div style="display:flex;justify-content:space-between">
                <span>{opt['label']}</span>
                <span style="font-size:13px;color:#888">{count}票 ({pct}%)</span>
              </div>
              <div style="margin-top:6px;height:4px;border-radius:4px;background:#e0e8ff">
                <div style="height:4px;border-radius:4px;background:#2563eb;width:{pct}%"></div>
              </div>
            </div>'''

    conn.close()
    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <div style="font-size:12px;color:#888;margin-bottom:8px">{fmt_datetime(sv['created_at'])}　回答 {total}名</div>
    <h1 style="margin-bottom:20px">{sv['title']}</h1>
    {option_btns}
  </div>
  <div style="text-align:center"><a href="/t/{code}/survey" style="font-size:13px;color:#888">← アンケート一覧</a></div>
</div>'''
    return page(sv['title'], body, code, active='survey')


@app.route('/t/<code>/admin/survey/new', methods=['GET', 'POST'])
def admin_new_survey(code):
    if not is_admin(code):
        return redirect(url_for('admin_login', code=code))
    team = get_team(code)
    if not team:
        return redirect('/')
    error = ''

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        options = [v.strip() for v in request.form.getlist('option') if v.strip()]
        if not title:
            error = '質問を入力してください'
        elif len(options) < 2:
            error = '選択肢を2つ以上入力してください'
        else:
            conn = get_db()
            sid = new_id()
            conn.execute('INSERT INTO surveys VALUES (?,?,?,?)', (sid, team['id'], title, now_str()))
            for i, label in enumerate(options):
                conn.execute('INSERT INTO survey_options VALUES (?,?,?,?)', (new_id(), sid, label, i))
            conn.commit()
            conn.close()
            return redirect(url_for('survey_list', code=code))

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>アンケートを作成</h1>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <form method="POST">
      <label>質問 *</label>
      <input type="text" name="title" placeholder="例：来週の練習に参加できますか？" required>
      <label>選択肢（最大6つ）</label>
      <input type="text" name="option" placeholder="例：参加できる" style="margin-bottom:8px">
      <input type="text" name="option" placeholder="例：参加できない" style="margin-bottom:8px">
      <input type="text" name="option" placeholder="例：未定" style="margin-bottom:8px">
      <input type="text" name="option" placeholder="（任意）" style="margin-bottom:8px">
      <input type="text" name="option" placeholder="（任意）" style="margin-bottom:8px">
      <input type="text" name="option" placeholder="（任意）" style="margin-bottom:8px">
      <button class="btn btn-blue btn-block" type="submit">作成する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/t/{code}/survey" style="font-size:13px;color:#888">← アンケート一覧</a></div>
</div>'''
    return page('アンケート作成', body, code, active='survey')


# ── App Feedback ─────────────────────────────────────────────────

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    sent = request.args.get('sent') == '1'
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        message = request.form.get('message', '').strip()
        if message:
            conn = get_db()
            conn.execute('INSERT INTO app_feedback VALUES (?,?,?,?)',
                         (new_id(), name, message, now_str()))
            conn.commit()
            conn.close()
            return redirect('/feedback?sent=1')

    body = f'''
<div class="container" style="max-width:480px">
  <div class="card">
    <h1>要望・フィードバック</h1>
    <p style="font-size:13px;color:#666;margin-bottom:20px">Rakへのご意見・ご要望・バグ報告をお送りください。<br>いただいた内容は開発の参考にします。</p>
    {'<div class="msg-ok">送信しました！ありがとうございます。</div>' if sent else ''}
    <form method="POST">
      <label>お名前（任意）</label>
      <input type="text" name="name" placeholder="例：田中">
      <label>メッセージ *</label>
      <textarea name="message" rows="5" placeholder="機能の要望・バグ報告・感想など何でもOKです" required></textarea>
      <button class="btn btn-blue btn-block" type="submit">送信する</button>
    </form>
  </div>
  <div style="text-align:center"><a href="/" style="font-size:13px;color:#aaa">← トップに戻る</a></div>
</div>'''
    return page('要望・フィードバック', body)


@app.route('/rak/feedback')
def rak_feedback_admin():
    pw = request.args.get('pw', '')
    admin_pw = os.environ.get('RAK_ADMIN_PW', 'rakadmin2026')
    if pw != admin_pw:
        body = '''
<div class="container" style="max-width:400px;padding-top:60px">
  <div class="card">
    <h1>管理者ログイン</h1>
    <form method="GET">
      <label>パスワード</label>
      <input type="password" name="pw" autofocus>
      <button class="btn btn-blue btn-block" type="submit">確認する</button>
    </form>
  </div>
</div>'''
        return page('Rak Admin', body)

    conn = get_db()
    items = conn.execute('SELECT * FROM app_feedback ORDER BY created_at DESC').fetchall()
    conn.close()

    rows = ''.join(f'''
    <div class="card-sm">
      <div style="font-size:12px;color:#aaa;margin-bottom:6px">{f["created_at"]}　{f["name"] or "匿名"}</div>
      <div style="white-space:pre-wrap;font-size:15px">{f["message"]}</div>
    </div>''' for f in items)

    body = f'''
<div class="container">
  <h1 style="margin-bottom:20px">フィードバック <span class="badge badge-blue">{len(items)}件</span></h1>
  {rows or '<div class="empty card">まだフィードバックはありません</div>'}
</div>'''
    return page('Rak フィードバック', body)


# ── Run ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3004))
    print(f'Rak アプリ起動中: http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=False)
