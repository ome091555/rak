import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from flask import Flask, redirect, render_template_string, request, session, url_for, jsonify

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
    ''')
    conn.commit()
    conn.close()

init_db()

# ── Helpers ───────────────────────────────────────────────────────

def new_id():
    return str(uuid.uuid4())[:8]

def now_str():
    return datetime.now(JST).strftime('%Y-%m-%d %H:%M')

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

FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&display=swap" rel="stylesheet">'

CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Noto Sans JP",sans-serif;background:#f0f4ff;color:#1a1a1a;font-size:15px;line-height:1.7;min-height:100vh}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
.nav{background:#fff;border-bottom:1px solid #e0e8ff;padding:0 20px;height:56px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:50}
.nav-logo{font-weight:900;font-size:18px;color:#2563eb;display:flex;align-items:center;gap:6px}
.nav-icon{width:28px;height:28px;background:#2563eb;border-radius:7px;color:#fff;font-size:13px;font-weight:900;display:flex;align-items:center;justify-content:center}
.nav-team{font-size:13px;color:#555;font-weight:500}
.nav-links{display:flex;gap:16px;margin-left:auto;align-items:center}
.nav-links a{font-size:13px;color:#555;padding:6px 10px;border-radius:8px}
.nav-links a:hover{background:#eff6ff;color:#2563eb;text-decoration:none}
.nav-links a.active{color:#2563eb;font-weight:700}
.container{max-width:680px;margin:0 auto;padding:24px 16px}
.card{background:#fff;border-radius:16px;padding:24px;box-shadow:0 1px 8px rgba(37,99,235,.07);margin-bottom:16px;border:1.5px solid #e0e8ff}
.card-sm{background:#fff;border-radius:12px;padding:16px 20px;border:1.5px solid #e0e8ff;margin-bottom:10px}
h1{font-size:22px;font-weight:900;margin-bottom:4px}
h2{font-size:18px;font-weight:700;margin-bottom:12px}
h3{font-size:15px;font-weight:700}
label{display:block;font-size:12px;font-weight:700;color:#2563eb;margin-bottom:5px;margin-top:14px}
label:first-of-type{margin-top:0}
input[type=text],input[type=password],input[type=date],input[type=time],textarea,select{width:100%;border:2px solid #dde6ff;border-radius:10px;padding:10px 14px;font-size:15px;outline:none;font-family:inherit;background:#fafcff}
input:focus,textarea:focus,select:focus{border-color:#2563eb;background:#fff}
textarea{resize:vertical;min-height:80px}
.btn{display:inline-block;padding:12px 24px;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;border:none;font-family:inherit;transition:.12s;text-decoration:none;text-align:center}
.btn-blue{background:#2563eb;color:#fff}
.btn-blue:hover{background:#1d4ed8;text-decoration:none;color:#fff}
.btn-outline{background:#fff;color:#2563eb;border:2px solid #2563eb}
.btn-outline:hover{background:#eff6ff;text-decoration:none}
.btn-gray{background:#f1f5f9;color:#555;border:none}
.btn-gray:hover{background:#e2e8f0;text-decoration:none;color:#555}
.btn-block{display:block;width:100%;margin-top:16px}
.btn-sm{padding:7px 14px;font-size:13px;border-radius:8px}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500}
.badge-green{background:#dcfce7;color:#16a34a}
.badge-red{background:#fee2e2;color:#dc2626}
.badge-gray{background:#f1f5f9;color:#64748b}
.badge-blue{background:#dbeafe;color:#1d4ed8}
.msg-ok{background:#f0fdf4;color:#16a34a;padding:12px 16px;border-radius:10px;margin-bottom:16px;font-weight:500;border:1.5px solid #bbf7d0}
.msg-err{background:#fef2f2;color:#dc2626;padding:12px 16px;border-radius:10px;margin-bottom:16px;font-weight:500}
.section-label{font-size:11px;font-weight:700;letter-spacing:.08em;color:#2563eb;background:#eff6ff;padding:3px 10px;border-radius:20px;display:inline-block;margin-bottom:14px}
.empty{text-align:center;padding:40px 20px;color:#888}
.row{display:flex;align-items:center;gap:10px}
.divider{border:none;border-top:1px solid #e0e8ff;margin:16px 0}
'''

def page(title, body, code=None, active=None):
    team = get_team(code) if code else None
    team_name = team['name'] if team else ''
    admin = is_admin(code) if code else False
    member = get_member(code) if code else ''

    nav_items = ''
    if code:
        nav_items = f'''
        <a href="/t/{code}/schedule" class="{'active' if active=='schedule' else ''}">📅 スケジュール</a>
        <a href="/t/{code}/notices" class="{'active' if active=='notices' else ''}">📢 お知らせ</a>
        '''
        if admin:
            nav_items += f'<a href="/t/{code}/admin/dash" class="{'active' if active=='admin' else ''}" style="color:#2563eb">⚙️ 管理</a>'
        elif member:
            nav_items += f'<span style="font-size:12px;color:#888;padding:6px 10px">👤 {member}</span>'

    return render_template_string(f'''<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
{FONT}<title>{title} | Rak</title>
<style>{CSS}</style></head><body>
<nav class="nav">
  <a class="nav-logo" href="{"/t/"+code if code else "/"}">
    <div class="nav-icon">R</div>Rak
  </a>
  {f'<span class="nav-team">{team_name}</span>' if team_name else ''}
  <div class="nav-links">{nav_items}</div>
</nav>
{body}
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
        sport = request.form.get('sport', '').strip()
        password = request.form.get('password', '').strip()
        if not name or not password:
            error = 'チーム名とパスワードを入力してください'
        else:
            team_id = new_id()
            code = new_id().upper()[:6]
            conn = get_db()
            conn.execute(
                'INSERT INTO teams VALUES (?,?,?,?,?,?)',
                (team_id, name, sport, code, password, now_str())
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
      <label>チーム名 *</label>
      <input type="text" name="name" placeholder="例：FCランウェイズ" required>
      <label>競技・スポーツ</label>
      <input type="text" name="sport" placeholder="例：サッカー、バスケ、水泳など">
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

@app.route('/t/<code>/schedule')
def schedule(code):
    team = get_team(code)
    if not team:
        return redirect('/')
    member = get_member(code)
    admin = is_admin(code)
    if not member and not admin:
        return redirect(url_for('team_portal', code=code))

    conn = get_db()
    today = datetime.now(JST).strftime('%Y-%m-%d')
    events = conn.execute(
        'SELECT * FROM events WHERE team_id=? AND event_date>=? ORDER BY event_date,event_time',
        (team['id'], today)
    ).fetchall()

    event_cards = ''
    for ev in events:
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
              <button name="status" value="attending" class="btn btn-sm {'btn-blue' if my_rsvp=='attending' else 'btn-outline'}" type="submit">✅ 出席</button>
              <button name="status" value="absent" class="btn btn-sm {'btn-red' if my_rsvp=='absent' else 'btn-gray'}" type="submit" style="{'background:#fee2e2;color:#dc2626;border:2px solid #dc2626' if my_rsvp=='absent' else ''}">❌ 欠席</button>
            </form>'''

        event_cards += f'''
        <div class="card-sm">
          <div class="row" style="flex-wrap:wrap;gap:6px">
            <div style="flex:1;min-width:0">
              <div style="font-weight:700;font-size:16px">{ev['title']}</div>
              <div style="font-size:13px;color:#555;margin-top:2px">
                📅 {fmt_date(ev['event_date'])}{' ' + ev['event_time'] if ev['event_time'] else ''}
                {('　📍 ' + ev['location']) if ev['location'] else ''}
              </div>
            </div>
            <div style="display:flex;gap:6px;align-items:center">
              <span class="badge badge-green">出席 {attending}</span>
              <span class="badge badge-red">欠席 {absent}</span>
            </div>
          </div>
          {f'<div style="font-size:13px;color:#666;margin-top:8px;background:#f8faff;padding:8px 12px;border-radius:8px">{ev["note"]}</div>' if ev['note'] else ''}
          {rsvp_btns}
        </div>'''
    conn.close()

    new_btn = f'<a href="/t/{code}/admin/events/new" class="btn btn-blue btn-sm">＋ 予定を追加</a>' if admin else ''
    body = f'''
<div class="container">
  <div class="row" style="margin-bottom:16px">
    <div><span class="section-label">📅 スケジュール</span></div>
    {new_btn}
  </div>
  {event_cards if events else '<div class="empty card">📭<br>予定はまだありません</div>'}
</div>'''
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
    conn.close()

    event_rows = ''.join(f'''
    <div class="card-sm row" style="justify-content:space-between">
      <div>
        <div style="font-weight:700">{ev['title']}</div>
        <div style="font-size:12px;color:#888">{fmt_date(ev['event_date'])}{' ' + ev['event_time'] if ev['event_time'] else ''}</div>
      </div>
      <a href="/t/{code}/admin/events/{ev['id']}" class="btn btn-sm btn-outline">詳細</a>
    </div>''' for ev in events) or '<div class="empty">予定なし</div>'

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
    <h2>✦ AI文章作成</h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">一言メモから、丁寧な連絡文を自動生成します</p>
    <a href="/t/{code}/admin/ai" class="btn btn-outline" style="display:block;text-align:center">AI文章作成を使う →</a>
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
    conn.close()

    attending = [r for r in rsvps if r['status'] == 'attending']
    absent = [r for r in rsvps if r['status'] == 'absent']

    def names(lst):
        return ''.join(f'<div style="font-size:14px;padding:5px 0;border-bottom:1px solid #f0f0f0">{r["member_name"]}</div>' for r in lst) or '<div style="font-size:13px;color:#aaa">なし</div>'

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
  <div style="text-align:center"><a href="/t/{code}/admin/dash" style="font-size:13px;color:#888">← ダッシュボード</a></div>
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

    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <h1>お知らせを作成</h1>
    {f'<div class="msg-err">{error}</div>' if error else ''}
    <div style="margin-bottom:16px">
      <a href="/t/{code}/admin/ai?redirect=notice" class="btn btn-sm btn-outline">✦ AIで下書きを作る</a>
    </div>
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

    use_btn = ''
    if result_title and result_body:
        import urllib.parse
        params = urllib.parse.urlencode({'title': result_title, 'body': result_body})
        use_btn = f'<a href="/t/{code}/admin/notices/new?{params}" class="btn btn-blue btn-block" style="margin-top:12px">このままお知らせとして送信 →</a>'

    body = f'''
<div class="container" style="max-width:540px">
  <div class="card">
    <div class="section-label">✦ AI文章作成</div>
    <h1>AIで下書きを作る</h1>
    <p style="color:#666;font-size:13px;margin-bottom:16px">一言メモを入力するだけで、丁寧な連絡文を自動生成します</p>
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

  {f'''<div class="card" style="border-color:#2563eb">
    <div class="section-label">生成結果</div>
    <h2>{result_title}</h2>
    <div style="white-space:pre-wrap;font-size:14px;color:#333;line-height:1.8;background:#f8faff;padding:14px;border-radius:10px;margin-top:8px">{result_body}</div>
    {use_btn}
  </div>''' if result_title else ''}

  <div style="text-align:center"><a href="/t/{code}/admin/dash" style="font-size:13px;color:#888">← ダッシュボード</a></div>
</div>'''
    return page('AI文章作成', body, code, active='admin')


# ── Run ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3004))
    print(f'Rak アプリ起動中: http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=False)
