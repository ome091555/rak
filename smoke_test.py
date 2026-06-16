#!/usr/bin/env python3
"""全ルート総当たりスモークテスト。
本番DBには触れず /tmp の隔離DBで全画面・全操作を実行し、500を検出する。
実行: python3 smoke_test.py
"""
import os, sys, traceback, tempfile

# 隔離DB
DB = os.path.join(tempfile.gettempdir(), 'rak_smoke.db')
for p in (DB, DB + '-wal', DB + '-shm'):
    if os.path.exists(p):
        os.remove(p)
os.environ['DATABASE'] = DB

import server
from datetime import datetime, timedelta

server.app.config['PROPAGATE_EXCEPTIONS'] = True
server.app.config['WTF_CSRF_ENABLED'] = False

CODE = 'SMOKE1'
VTOKEN = 'viewtok123'
MEMBERS = ['田中太郎', '佐藤花子', '鈴木一郎']

failures = []   # (label, status, tb)
results = []     # (label, status)


def seed():
    conn = server.get_db()
    tid = server.new_id()
    future = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    # team (pro, trialなし=有料想定) 全列明示
    cols = [r[1] for r in conn.execute('PRAGMA table_info(teams)').fetchall()]
    vals = {
        'id': tid, 'name': 'スモークFC', 'sport': 'サッカー', 'team_code': CODE,
        'admin_password': server.hash_pw('pass1234') if hasattr(server, 'hash_pw') else 'x',
        'created_at': server.now_str(), 'plan': 'pro', 'stripe_customer_id': '',
        'stripe_subscription_id': '', 'admin_memo': '', 'admin_email': 'a@example.com',
        'trial_end': future, 'viewer_token': VTOKEN,
    }
    conn.execute(f"INSERT INTO teams ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                 [vals.get(c, '') for c in cols])
    for i, name in enumerate(MEMBERS):
        mcols = [r[1] for r in conn.execute('PRAGMA table_info(members)').fetchall()]
        mv = {'id': server.new_id(), 'team_id': tid, 'name': name,
              'number': str(i + 1), 'position': 'MF', 'created_at': server.now_str()}
        conn.execute(f"INSERT INTO members ({','.join(mcols)}) VALUES ({','.join('?' for _ in mcols)})",
                     [mv.get(c, '') for c in mcols])
    conn.commit()
    conn.close()
    return tid


def admin_client():
    c = server.app.test_client()
    with c.session_transaction() as s:
        s[f'admin_{CODE}'] = True
    return c


def member_client():
    c = server.app.test_client()
    with c.session_transaction() as s:
        s[f'member_{CODE}'] = MEMBERS[0]
    c.set_cookie('rak_ans_' + CODE, MEMBERS[0])
    return c


def hit(c, method, path, label, data=None, ct=None):
    try:
        kw = {}
        if data is not None:
            kw['data'] = data
        if method == 'GET':
            r = c.get(path, **kw)
        else:
            r = c.post(path, **kw)
        results.append((label, r.status_code))
        if r.status_code >= 500:
            failures.append((label + ' ' + path, r.status_code,
                             r.get_data(as_text=True)[:1500]))
        return r
    except Exception:
        tb = traceback.format_exc()
        results.append((label, 'EXC'))
        failures.append((label + ' ' + path, 'EXC', tb))
        return None


def get_first(table, where=''):
    conn = server.get_db()
    row = conn.execute(f'SELECT id FROM {table} {where} LIMIT 1').fetchone()
    conn.close()
    return row['id'] if row else None


def main():
    tid = seed()
    A = admin_client()
    M = member_client()
    P = server.app.test_client()  # 公開(未ログイン)

    # ---- 1. 公開・静的 ----
    for path in ['/', '/create', '/login', '/forgot-password', '/feedback',
                 '/legal/privacy', '/legal/terms', '/legal/tokushoho',
                 '/manifest.json', '/sw.js', '/robots.txt', '/sitemap.xml',
                 '/icon.svg', '/push/vapid-public-key']:
        hit(P, 'GET', path, 'public GET')

    # ---- 2. 作成系POST(管理者) ----
    hit(A, 'POST', f'/t/{CODE}/admin/events/new', 'new_event', data={
        'title': '練習試合', 'event_date': '2026-06-20', 'event_time': '10:00',
        'end_date': '2026-06-20', 'end_time': '12:00', 'location': '市営グラウンド',
        'note': '集合9:45', 'rsvp_mode': 'both', 'event_color': '#16A34A'})
    hit(A, 'POST', f'/t/{CODE}/admin/fees/new', 'new_fee', data={
        'title': '6月会費', 'amount': '3,000円', 'due_date': '2026-06-30',
        'note': '月会費', 'members': MEMBERS})
    hit(A, 'POST', f'/t/{CODE}/admin/uniforms', 'new_uniform', data={
        'name': 'ホームユニ2026', 'description': '10月配布'})
    hit(A, 'POST', f'/t/{CODE}/admin/memos/new', 'new_memo', data={
        'title': '監督メモ', 'content': '次節の戦術について'})
    hit(A, 'POST', f'/t/{CODE}/admin/notices/new', 'new_notice', data={
        'title': 'お知らせ', 'body': '今週末の練習について'})
    hit(A, 'POST', f'/t/{CODE}/admin/survey/new', 'new_survey', data={
        'title': '懇親会の日程', 'option': ['6/25', '6/26', '6/27']})
    hit(A, 'POST', f'/t/{CODE}/admin/orders/new', 'new_order', data={
        'title': '応援グッズ注文', 'description': 'タオル等', 'deadline': '2026-07-01',
        'field_label': ['サイズ', '枚数'], 'field_type': ['select', 'number'],
        'field_options': ['S,M,L', '']})
    hit(A, 'POST', f'/t/{CODE}/admin/ledger', 'ledger_add', data={
        'action': 'add', 'type': 'income', 'title': '会費収入', 'amount': '30000',
        'category': '会費', 'entry_date': '2026-06-15', 'memo': ''})
    hit(A, 'POST', f'/t/{CODE}/admin/members', 'member_add', data={
        'action': 'add', 'last_name': '高橋', 'first_name': '健', 'number': '10', 'position': 'FW'})

    # 作成済みIDを取得
    eid = get_first('events', f"WHERE team_id='{tid}'")
    fid = get_first('fees', f"WHERE team_id='{tid}'")
    uid = get_first('uniforms', f"WHERE team_id='{tid}'")
    mid = get_first('memos' if table_exists('memos') else 'admin_memos')
    nid = get_first('notices', f"WHERE team_id='{tid}'")
    sid = get_first('surveys', f"WHERE team_id='{tid}'")
    ofid = get_first('order_forms', f"WHERE team_id='{tid}'")
    memberid = get_first('members', f"WHERE team_id='{tid}'")

    # ---- 3. 管理GET(一覧・詳細・編集・CSV) ----
    admin_gets = [
        f'/t/{CODE}/admin/dash', f'/t/{CODE}/admin/members',
        f'/t/{CODE}/admin/fees', f'/t/{CODE}/admin/memos',
        f'/t/{CODE}/admin/ledger', f'/t/{CODE}/admin/settings',
        f'/t/{CODE}/admin/ai', f'/t/{CODE}/admin/ai-schedule',
        f'/t/{CODE}/admin/uniforms', f'/t/{CODE}/admin/schedule/excel',
        f'/t/{CODE}/admin/events/new', f'/t/{CODE}/admin/fees/new',
        f'/t/{CODE}/admin/orders/new', f'/t/{CODE}/admin/memos/new',
        f'/t/{CODE}/admin/notices/new', f'/t/{CODE}/admin/survey/new',
    ]
    if eid:
        admin_gets += [f'/t/{CODE}/admin/events/{eid}', f'/t/{CODE}/admin/events/{eid}/edit',
                       f'/t/{CODE}/admin/events/{eid}/csv']
    if fid:
        admin_gets += [f'/t/{CODE}/admin/fees/{fid}', f'/t/{CODE}/admin/fees/{fid}/edit']
    if uid:
        admin_gets += [f'/t/{CODE}/admin/uniforms/{uid}']
    if mid:
        admin_gets += [f'/t/{CODE}/admin/memos/{mid}', f'/t/{CODE}/admin/memos/{mid}/edit']
    if ofid:
        admin_gets += [f'/t/{CODE}/admin/orders/{ofid}/edit', f'/t/{CODE}/admin/orders/{ofid}/csv']
    if memberid:
        admin_gets += [f'/t/{CODE}/admin/members/{memberid}/edit']
    for path in admin_gets:
        hit(A, 'GET', path, 'admin GET')

    # ---- 4. 編集・更新POST ----
    if eid:
        hit(A, 'POST', f'/t/{CODE}/admin/events/{eid}/edit', 'edit_event', data={
            'title': '練習試合(変更)', 'event_date': '2026-06-21', 'event_time': '11:00',
            'end_date': '2026-06-21', 'end_time': '13:00', 'location': 'X', 'note': '',
            'rsvp_mode': 'attend', 'event_color': '#2563EB'})
    if fid:
        hit(A, 'POST', f'/t/{CODE}/admin/fees/{fid}/edit', 'edit_fee', data={
            'title': '6月会費(変更)', 'amount': '￥3,500', 'due_date': '2026-07-05', 'note': ''})
        hit(A, 'POST', f'/t/{CODE}/admin/fees/{fid}', 'fee_toggle', data={
            'member_name': MEMBERS[0], 'paid': '1'})
    if uid:
        hit(A, 'POST', f'/t/{CODE}/admin/uniforms/{uid}', 'uniform_save', data={
            f'size_{MEMBERS[0]}': '140', f'number_{MEMBERS[0]}': '7',
            f'qty_{MEMBERS[0]}': '2', f'received_{MEMBERS[0]}': 'on',
            f'notes_{MEMBERS[0]}': 'OK'})
    if mid:
        hit(A, 'POST', f'/t/{CODE}/admin/memos/{mid}/edit', 'edit_memo', data={
            'title': 'メモ(変更)', 'content': '更新'})
    if ofid:
        hit(A, 'POST', f'/t/{CODE}/admin/orders/{ofid}/edit', 'edit_order', data={
            'title': 'グッズ(変更)', 'description': '', 'deadline': '2026-07-10'})
    if memberid:
        hit(A, 'POST', f'/t/{CODE}/admin/members/{memberid}/edit', 'edit_member', data={
            'last_name': '田中', 'first_name': '太郎', 'number': '1', 'position': 'GK'})
    hit(A, 'POST', f'/t/{CODE}/admin/settings', 'settings_profile', data={
        'action': 'profile', 'name': 'スモークFC改', 'email': 'b@example.com'})

    # ---- 5. メンバー画面GET ----
    member_gets = [
        f'/t/{CODE}', f'/t/{CODE}/home', f'/t/{CODE}/members', f'/t/{CODE}/schedule',
        f'/t/{CODE}/fees', f'/t/{CODE}/notices', f'/t/{CODE}/orders',
        f'/t/{CODE}/survey', f'/t/{CODE}/uniforms', f'/t/{CODE}/help',
        f'/t/{CODE}/upgrade',
    ]
    if nid:
        member_gets.append(f'/t/{CODE}/notices/{nid}')
    if sid:
        member_gets.append(f'/t/{CODE}/survey/{sid}')
    if ofid:
        member_gets.append(f'/t/{CODE}/orders/{ofid}')
    for path in member_gets:
        hit(M, 'GET', path, 'member GET')

    # ---- 6. 公開トークンページ ----
    pub_gets = [
        f'/t/{CODE}/view/{VTOKEN}', f'/t/{CODE}/answer/{VTOKEN}',
        f'/t/{CODE}/pay-answer/{VTOKEN}',
    ]
    if ofid:
        pub_gets.append(f'/t/{CODE}/order-answer/{VTOKEN}/{ofid}')
    for path in pub_gets:
        hit(P, 'GET', path, 'public token GET')

    # ---- 7. 公開トークンPOST(回答・申告) ----
    Pc = server.app.test_client()
    Pc.set_cookie('rak_ans_' + CODE, MEMBERS[0])
    if eid:
        hit(Pc, 'POST', f'/t/{CODE}/answer/{VTOKEN}/rsvp/{eid}', 'answer_rsvp',
            data={'status': 'yes'})
        hit(M, 'POST', f'/t/{CODE}/rsvp/{eid}', 'member_rsvp', data={'status': 'no'})
    if fid:
        hit(Pc, 'POST', f'/t/{CODE}/pay-answer/{VTOKEN}/report/{fid}', 'pay_report', data={})
    if ofid:
        hit(Pc, 'POST', f'/t/{CODE}/order-answer/{VTOKEN}/{ofid}/submit', 'order_submit',
            data={'name': MEMBERS[0]})
    if sid:
        oid = get_first('survey_options', f"WHERE survey_id='{sid}'")
        if oid:
            hit(M, 'POST', f'/t/{CODE}/survey/{sid}', 'survey_vote', data={'option_id': oid})

    # ---- 8. エッジ入力（実ユーザーの“雑な”入力で落ちないか）----
    # 会費：対象0人・空金額・全角金額・記号入り
    hit(A, 'POST', f'/t/{CODE}/admin/fees/new', 'edge_fee_no_members', data={
        'title': '対象なし会費', 'amount': '', 'due_date': '', 'note': ''})
    hit(A, 'POST', f'/t/{CODE}/admin/fees/new', 'edge_fee_zenkaku', data={
        'title': '全角会費', 'amount': '３０００円', 'due_date': '2026/6/30',
        'note': '', 'members': MEMBERS})
    hit(A, 'POST', f'/t/{CODE}/admin/fees/new', 'edge_fee_text', data={
        'title': '文字金額', 'amount': '未定', 'members': [MEMBERS[0]]})
    # 予定：タイトルのみ・日付空
    hit(A, 'POST', f'/t/{CODE}/admin/events/new', 'edge_event_minimal', data={
        'title': '日付なし予定'})
    hit(A, 'POST', f'/t/{CODE}/admin/events/new', 'edge_event_empty', data={})
    # ユニフォーム：名前空（バリデーションで弾く想定・落ちない）
    hit(A, 'POST', f'/t/{CODE}/admin/uniforms', 'edge_uniform_empty', data={'name': ''})
    # ユニフォーム保存：数量に全角/空
    if uid:
        hit(A, 'POST', f'/t/{CODE}/admin/uniforms/{uid}', 'edge_uniform_qty', data={
            f'size_{MEMBERS[1]}': '110', f'qty_{MEMBERS[1]}': '３', f'number_{MEMBERS[1]}': ''})
    # 台帳：金額に記号・全角、カテゴリ空
    hit(A, 'POST', f'/t/{CODE}/admin/ledger', 'edge_ledger_symbol', data={
        'action': 'add', 'type': 'expense', 'title': '備品', 'amount': '￥1,2３4円',
        'category': '', 'entry_date': '', 'memo': ''})
    # メンバー：空・番号に全角
    hit(A, 'POST', f'/t/{CODE}/admin/members', 'edge_member_empty', data={'action': 'add'})
    hit(A, 'POST', f'/t/{CODE}/admin/members', 'edge_member_zenkaku', data={
        'action': 'add', 'last_name': '山田', 'first_name': '', 'number': '９', 'position': ''})
    # アンケート：選択肢空/1個
    hit(A, 'POST', f'/t/{CODE}/admin/survey/new', 'edge_survey_empty', data={
        'title': '空アンケート', 'option': ['']})
    # 注文：項目なし
    hit(A, 'POST', f'/t/{CODE}/admin/orders/new', 'edge_order_nofields', data={
        'title': '項目なし注文', 'description': '', 'deadline': ''})
    # 設定：パスワード変更（不一致）
    hit(A, 'POST', f'/t/{CODE}/admin/settings', 'edge_settings_pw', data={
        'action': 'password', 'current_password': 'x', 'new_password': 'y',
        'confirm_password': 'z'})
    # フィードバック・プロモ
    hit(P, 'POST', '/feedback', 'edge_feedback', data={
        'name': '', 'email': '', 'message': '', 'subject': ''})
    hit(A, 'POST', f'/t/{CODE}/upgrade/promo', 'edge_promo', data={'promo': 'INVALID'})

    # ---- report ----
    print('\n' + '=' * 64)
    print(f'実行ルート数: {len(results)}   失敗(500/例外): {len(failures)}')
    print('=' * 64)
    if failures:
        for label, st, tb in failures:
            print(f'\n❌ [{st}] {label}')
            print('-' * 50)
            print(tb[-1200:])
        sys.exit(1)
    else:
        print('✅ 全ルート 500/例外なし')


def table_exists(name):
    conn = server.get_db()
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    conn.close()
    return r is not None


if __name__ == '__main__':
    main()
