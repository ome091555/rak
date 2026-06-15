# Rak 法的文書（利用規約・プライバシーポリシー・特定商取引法に基づく表記）
# server.py から import して各ルートで配信する

SELLER_NAME = "奥田芽衣"
SELLER_EMAIL = "support@rakapp.jp"
SERVICE_NAME = "Rak"
PRICE_MONTHLY = "980"
PRICE_YEARLY = "9,800"
LAST_UPDATED = "2026年6月15日"


def _wrap(title, body_html):
    return f'''<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} | {SERVICE_NAME}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,"Hiragino Kaku Gothic ProN",sans-serif;background:#f7f8fa;color:#1a1a1a;line-height:1.9;font-size:15px}}
.wrap{{max-width:720px;margin:0 auto;padding:40px 20px 80px}}
h1{{font-size:24px;margin-bottom:8px}}
.updated{{color:#888;font-size:13px;margin-bottom:32px}}
h2{{font-size:17px;margin:32px 0 10px;padding-top:16px;border-top:1px solid #e5e7eb}}
p,li{{color:#333;font-size:14px}}
ul,ol{{padding-left:22px;margin:8px 0}}
li{{margin-bottom:6px}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}}
th,td{{border:1px solid #e5e7eb;padding:10px 12px;text-align:left;vertical-align:top}}
th{{background:#f0f2f5;width:34%;font-weight:600}}
a{{color:#2563eb}}
.back{{display:inline-block;margin-top:40px;color:#888;font-size:13px;text-decoration:none}}
</style></head>
<body><div class="wrap">{body_html}
<a href="/" class="back">← トップに戻る</a>
</div></body></html>'''


def terms_html():
    body = f'''
<h1>利用規約</h1>
<div class="updated">最終更新日：{LAST_UPDATED}</div>

<p>本利用規約（以下「本規約」）は、{SELLER_NAME}（以下「運営者」）が提供するチーム運営支援サービス「{SERVICE_NAME}」（以下「本サービス」）の利用条件を定めるものです。利用者は本規約に同意の上、本サービスを利用するものとします。</p>

<h2>第1条（適用）</h2>
<p>本規約は、本サービスの利用に関わる運営者と利用者との一切の関係に適用されます。</p>

<h2>第2条（利用登録）</h2>
<ul>
<li>本サービスのアカウント登録はチームの管理者（運営担当者）のみが行うものとします。チームメンバーはアカウント登録なしに、管理者が共有するリンクから出欠回答等の機能を利用できます。</li>
<li>運営者は、登録希望者に一定の事由があると判断した場合、登録を拒否することがあります。</li>
</ul>

<h2>第3条（料金および支払方法）</h2>
<ul>
<li>本サービスの有料プラン「{SERVICE_NAME} Pro」の利用料金は、月額{PRICE_MONTHLY}円（税込）または年額{PRICE_YEARLY}円（税込）とします。</li>
<li>支払いは、クレジットカード（決済代行：Stripe, Inc.）による継続課金（サブスクリプション）とします。</li>
<li>料金は前払いとし、解約しない限り自動的に更新・課金されます。</li>
</ul>

<h2>第4条（解約・返金）</h2>
<ul>
<li>利用者はいつでも本サービスの有料プランを解約できます。解約は本サービス内の設定または運営者への連絡により行います。</li>
<li>解約した場合、次回更新日以降の課金は停止されます。すでに支払われた料金は、法令に定める場合を除き返金されません。</li>
<li>解約後も、当該課金期間の終了までは有料機能を利用できます。</li>
</ul>

<h2>第5条（禁止事項）</h2>
<p>利用者は、以下の行為をしてはなりません。</p>
<ul>
<li>法令または公序良俗に違反する行為</li>
<li>運営者または第三者の権利・利益を侵害する行為</li>
<li>本サービスの運営を妨害する行為</li>
<li>不正アクセスやそれを試みる行為</li>
<li>他の利用者の情報を不正に収集・利用する行為</li>
</ul>

<h2>第6条（本サービスの停止・変更）</h2>
<p>運営者は、利用者への事前通知なく、本サービスの内容を変更し、または提供を停止することができます。これにより利用者に生じた損害について、運営者は責任を負いません。</p>

<h2>第7条（免責事項）</h2>
<ul>
<li>運営者は、本サービスに事実上または法律上の瑕疵がないことを保証しません。</li>
<li>運営者は、本サービスの利用により利用者に生じた損害について、運営者の故意または重過失による場合を除き、責任を負いません。</li>
</ul>

<h2>第8条（個人情報の取扱い）</h2>
<p>運営者は、利用者の個人情報を別途定める「プライバシーポリシー」に従い適切に取り扱います。</p>

<h2>第9条（準拠法・管轄）</h2>
<p>本規約の解釈には日本法を準拠法とし、本サービスに関して紛争が生じた場合には、運営者の住所地を管轄する裁判所を専属的合意管轄裁判所とします。</p>

<h2>お問い合わせ</h2>
<p>本規約に関するお問い合わせは {SELLER_EMAIL} までご連絡ください。</p>
'''
    return _wrap("利用規約", body)


def privacy_html():
    body = f'''
<h1>プライバシーポリシー</h1>
<div class="updated">最終更新日：{LAST_UPDATED}</div>

<p>{SELLER_NAME}（以下「運営者」）は、チーム運営支援サービス「{SERVICE_NAME}」（以下「本サービス」）における利用者の個人情報を、以下の方針に基づき適切に取り扱います。</p>

<h2>1. 取得する情報</h2>
<ul>
<li>管理者アカウントのメールアドレス・パスワード（ハッシュ化して保存）、チーム名、チーム情報</li>
<li>管理者が入力したメンバー氏名、スケジュール、出欠回答、集金・会計記録等のチーム運営情報</li>
<li>チームメンバーが出欠回答リンクから送信した回答内容（名前の選択・出欠の選択）。メンバーはアカウント登録不要で、個人アカウントの情報は取得しません。</li>
<li>有料プラン利用時の決済関連情報（クレジットカード情報そのものは運営者は保持せず、決済代行会社が処理します）</li>
<li>サービス利用に伴うアクセスログ（IPアドレス、ブラウザ情報、操作ログ等）。これらはサービス基盤である Railway, Inc. のサーバーに記録されます。Google Analytics 等の外部解析ツールは現在使用していません。</li>
<li>本サービスはセッション維持のために Cookie（サーバーサイドセッション）を使用します。また出欠回答リンクでは、前回選択した名前を記憶するためのCookieを端末に保存します（最大180日）。広告目的のサードパーティ Cookie は使用していません。</li>
</ul>

<h2>2. 利用目的</h2>
<ul>
<li>本サービスの提供・運営・本人確認のため</li>
<li>利用料金の請求・決済のため</li>
<li>お問い合わせ対応、重要なお知らせの連絡のため</li>
<li>サービスの改善・新機能の開発のため</li>
</ul>

<h2>3. 第三者提供</h2>
<p>運営者は、以下の場合を除き、利用者の同意なく個人情報を第三者に提供しません。</p>
<ul>
<li>法令に基づく場合</li>
<li>人の生命・身体・財産の保護に必要な場合</li>
</ul>

<h2>4. 業務委託（決済代行）</h2>
<p>有料プランの決済処理は Stripe, Inc. に委託しています。クレジットカード情報は同社が直接取得・管理し、運営者はカード番号等を保持しません。</p>

<h2>5. 個人情報の管理</h2>
<p>運営者は、個人情報の漏えい・滅失・毀損の防止その他の安全管理のために必要かつ適切な措置を講じます。</p>

<h2>6. 未成年者の個人情報</h2>
<p>本サービスは少年野球・少年サッカー等のジュニアスポーツチームでの利用を想定しており、未成年者の氏名等が管理者によって入力される場合があります。チームの管理者は、メンバーの氏名等を入力する前に本人・保護者の同意を確認してください。未成年者に関する個人情報の開示・訂正・削除の請求は、保護者からも受け付けます。</p>

<h2>7. 退会・チーム削除時のデータ取扱い</h2>
<p>チームが削除された場合、当該チームに紐づく全データ（メンバー情報、スケジュール、集金記録等）は削除後30日以内にサーバーから削除されます。有料プランを解約した場合、アカウント自体は残り、データは保持されます。データの削除を希望する場合は {SELLER_EMAIL} までご連絡ください。</p>

<h2>8. 開示・訂正・削除</h2>
<p>利用者は、運営者に対し自己の個人情報の開示・訂正・削除を請求できます。請求は {SELLER_EMAIL} までご連絡ください。本人確認の上、合理的な期間内に対応します。</p>

<h2>9. お問い合わせ窓口</h2>
<p>個人情報の取扱いに関するお問い合わせ：{SELLER_EMAIL}</p>
'''
    return _wrap("プライバシーポリシー", body)


def tokushoho_html():
    body = f'''
<h1>特定商取引法に基づく表記</h1>
<div class="updated">最終更新日：{LAST_UPDATED}</div>

<table>
<tr><th>販売事業者</th><td>{SELLER_NAME}</td></tr>
<tr><th>運営責任者</th><td>{SELLER_NAME}</td></tr>
<tr><th>所在地</th><td>請求があったときは遅滞なく開示します。ご希望の場合は下記連絡先までお問い合わせください。</td></tr>
<tr><th>電話番号</th><td>請求があったときは遅滞なく開示します。ご希望の場合は下記連絡先までお問い合わせください。</td></tr>
<tr><th>メールアドレス</th><td>{SELLER_EMAIL}</td></tr>
<tr><th>販売価格</th><td>{SERVICE_NAME} Pro：月額{PRICE_MONTHLY}円（税込） / 年額{PRICE_YEARLY}円（税込）</td></tr>
<tr><th>商品代金以外の必要料金</th><td>インターネット接続料金・通信料金等はお客様のご負担となります。</td></tr>
<tr><th>支払方法</th><td>クレジットカード決済（決済代行：Stripe, Inc.）</td></tr>
<tr><th>支払時期</th><td>月額プランは申込日を起点に毎月、年額プランは毎年、自動課金されます。前払い制です。</td></tr>
<tr><th>サービス提供時期</th><td>決済完了後、直ちに有料機能をご利用いただけます。</td></tr>
<tr><th>解約・返金について</th><td>本サービス内の設定または下記連絡先からいつでも解約できます。解約後は次回更新日以降の課金が停止されます。サービスの性質上、既にお支払い済みの料金の返金は致しかねます（法令に定めがある場合を除く）。解約後も当該課金期間の終了まで有料機能をご利用いただけます。</td></tr>
<tr><th>動作環境</th><td>最新版のWebブラウザ（Safari, Chrome等）でご利用ください。</td></tr>
</table>
'''
    return _wrap("特定商取引法に基づく表記", body)
