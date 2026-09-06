import os
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as OpenpyxlImage
import pptx
from pptx.util import Inches as PptxInches, Pt as PptxPt
from pptx.dml.color import RGBColor as PptxRGBColor
import fitz
from PIL import Image, ImageDraw, ImageFont
import io

OUTPUT_DIR = r"E:\AutomationTranslate\sample_documents\test_suite_google_drive"
os.makedirs(OUTPUT_DIR, exist_ok=True)
IMG_DIR = os.path.join(OUTPUT_DIR, "assets")
os.makedirs(IMG_DIR, exist_ok=True)

def create_architecture_diagram(path: str):
    """Generates a clean IT Architecture Diagram image with Japanese labels."""
    width, height = 900, 480
    im = Image.new("RGB", (width, height), color="#0f172a") # Slate 900
    draw = ImageDraw.Draw(im)

    # Draw grid or title background
    draw.rectangle([20, 20, 880, 70], fill="#1e293b", outline="#38bdf8", width=2)
    draw.text((40, 32), "システムアーキテクチャ概要図 (System Architecture Diagram)", fill="#f8fafc")

    # Draw Component 1: Client Layer
    draw.rectangle([40, 110, 240, 220], fill="#1e293b", outline="#60a5fa", width=2)
    draw.text((60, 125), "【クライアント層】", fill="#93c5fd")
    draw.text((60, 155), "・Webブラウザ (React)", fill="#e2e8f0")
    draw.text((60, 185), "・モバイルアプリ (iOS/Android)", fill="#e2e8f0")

    # Arrow 1 -> API Gateway
    draw.line([(240, 165), (340, 165)], fill="#38bdf8", width=3)
    draw.polygon([(340, 165), (330, 158), (330, 172)], fill="#38bdf8")
    draw.text((250, 140), "HTTPS / WSS", fill="#38bdf8")

    # Draw Component 2: API Gateway & Auth
    draw.rectangle([340, 100, 560, 320], fill="#1e293b", outline="#f59e0b", width=2)
    draw.text((360, 115), "【API Gateway & 認証】", fill="#fbbf24")
    draw.text((360, 150), "・OAuth2 / OIDC 検証", fill="#e2e8f0")
    draw.text((360, 180), "・レート制限 (Rate Limiter)", fill="#e2e8f0")
    draw.text((360, 210), "・ルーティングエンジン", fill="#e2e8f0")
    draw.text((360, 240), "・SSL/TLS 暗号化終端", fill="#e2e8f0")
    draw.text((360, 270), "・WAF (Web Application Firewall)", fill="#e2e8f0")

    # Arrow 2 -> Microservices
    draw.line([(560, 165), (660, 165)], fill="#38bdf8", width=3)
    draw.polygon([(660, 165), (650, 158), (650, 172)], fill="#38bdf8")
    draw.text((570, 140), "gRPC / REST", fill="#38bdf8")

    # Draw Component 3: Backend Microservices
    draw.rectangle([660, 100, 860, 360], fill="#1e293b", outline="#34d399", width=2)
    draw.text((675, 115), "【マイクロサービス群】", fill="#6ee7b7")
    draw.text((675, 150), "・ユーザー認証サービス", fill="#e2e8f0")
    draw.text((675, 180), "・翻訳エンジンサービス", fill="#e2e8f0")
    draw.text((675, 210), "・用語集管理 (Glossary)", fill="#e2e8f0")
    draw.text((675, 240), "・翻訳メモリ (TM) ベクトル検索", fill="#e2e8f0")
    draw.text((675, 270), "・非同期ジョブワーカー", fill="#e2e8f0")
    draw.text((675, 300), "・監査ログ・通知サービス", fill="#e2e8f0")

    # Database layer at bottom
    draw.rectangle([340, 360, 560, 450], fill="#1e293b", outline="#a855f7", width=2)
    draw.text((360, 375), "【データ永続化層】", fill="#d8b4fe")
    draw.text((360, 405), "・PostgreSQL / SQLite WAL", fill="#e2e8f0")
    draw.text((360, 425), "・Redis Cache & Qdrant Vector DB", fill="#e2e8f0")

    # Arrow down to DB
    draw.line([(450, 320), (450, 360)], fill="#a855f7", width=2)

    im.save(path, quality=95)
    print(f"Generated architecture diagram at {path}")

def create_cost_chart_diagram(path: str):
    """Generates a chart image representing Cloud Infrastructure Estimates."""
    width, height = 700, 350
    im = Image.new("RGB", (width, height), color="#0f172a")
    draw = ImageDraw.Draw(im)

    draw.rectangle([15, 15, 685, 60], fill="#1e293b", outline="#38bdf8", width=1)
    draw.text((30, 28), "クラウドインフラ月次コスト内訳 (Monthly Cloud Cost Breakdown)", fill="#f8fafc")

    categories = [
        ("AWS ECS / EKS (Compute)", 45, "#38bdf8"),
        ("RDS PostgreSQL (Database)", 25, "#34d399"),
        ("AI API Quotas (Gemini/Groq)", 18, "#fbbf24"),
        ("Storage S3 & Backup", 7, "#a855f7"),
        ("Network & NAT Gateway", 5, "#f43f5e")
    ]

    # Draw Bar Chart
    start_y = 90
    for name, pct, color in categories:
        bar_w = int((pct / 50.0) * 350)
        draw.text((30, start_y), name, fill="#cbd5e1")
        draw.rectangle([260, start_y, 260 + bar_w, start_y + 24], fill=color)
        draw.text((270 + bar_w, start_y + 4), f"{pct}% (約 ¥{pct * 15000:,})", fill="#f8fafc")
        start_y += 45

    im.save(path, quality=95)
    print(f"Generated cost chart at {path}")

# 1. DOCX (Google Docs)
def create_sample_docx(img_path: str):
    doc = docx.Document()

    # Document Title
    h1 = doc.add_heading("次世代クラウド認証システム仕様書", level=0)
    doc.add_paragraph("プロジェクト: ABC Banking System 刷新計画 · 作成日: 2026年9月 · 分類: 社内極秘")

    # Section 1
    doc.add_heading("1. システム概要と目的", level=1)
    doc.add_paragraph(
        "本システムは、BrSEおよび開発チーム向けに高信頼・低遅延なOAuth2認証基盤を提供することを目的とします。"
        "金融機関向けセキュリティ基準に準拠し、PKCE (Proof Key for Code Exchange) による認可コード横取り攻撃の防止対策を実施します。"
    )

    # Insert Image
    if os.path.exists(img_path):
        doc.add_heading("2. システム構成アーキテクチャ図", level=1)
        doc.add_paragraph("以下はシステム全体の論理構成図および各レイヤー間の通信プロトコル仕様です：")
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_img.add_run()
        run.add_picture(img_path, width=Inches(6.0))
        caption = doc.add_paragraph("図 2.1: クラウド認証基盤のコンポーネント構成図")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Table
    doc.add_heading("3. 主要APIエンドポイント仕様一覧", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = "メソッド"
    hdr[1].text = "URI エンドポイント"
    hdr[2].text = "認証要否"
    hdr[3].text = "機能説明と処理概要"

    apis = [
        ("POST", "/api/v2/oauth/authorize", "不要", "認可コードの発行処理。PKCEパラメータ code_challenge を必須検証。"),
        ("POST", "/api/v2/oauth/token", "不要", "アクセストークンおよびリフレッシュトークンの発行。"),
        ("GET", "/api/v2/users/me", "必須 (Bearer)", "ログイン中ユーザーのプロファイル情報および権限リストの取得。"),
        ("POST", "/api/v2/auth/revoke", "必須", "トークンの失効処理およびアクティブセッションの即時切断。"),
        ("GET", "/api/v2/health", "不要", "ロードバランサー向け死活監視ヘルスチェックエンドポイント。")
    ]
    for m, u, a, desc in apis:
        row = table.add_row().cells
        row[0].text = m
        row[1].text = u
        row[2].text = a
        row[3].text = desc

    doc.add_heading("4. 例外処理およびエラーコード定義", level=1)
    doc.add_paragraph(
        "システム内で発生するHTTP 4xxおよび5xxエラーは、すべてRFC 7807 (Problem Details for HTTP APIs) に準拠したJSONフォーマットで返却します。"
        "クライアント側は `error_code` に基づいて自動リトライまたは再認証プロンプトを表示する必要があります。"
    )

    out_path = os.path.join(OUTPUT_DIR, "01_DacTa_XacThuc_OAuth2_JA.docx")
    doc.save(out_path)
    print(f"Created DOCX at {out_path}")

# 2. XLSX (Google Sheets)
def create_sample_xlsx(chart_img_path: str):
    wb = openpyxl.Workbook()

    # Sheet 1: Infrastructure Cost
    ws1 = wb.active
    ws1.title = "Infra_Cost (インフラ試算)"
    
    headers1 = ["No.", "リソース項目 (Resource)", "サービス種別", "スペック / 構成", "数量", "単価 (月額/円)", "月額小計 (円)", "備考"]
    ws1.append(headers1)

    items1 = [
        [1, "ECS Fargate コンテナクラスター", "AWS Compute", "4 vCPU / 16GB RAM", 4, 32000, "=E2*F2", "本番Web/APIワーカー"],
        [2, "Aurora PostgreSQL (Multi-AZ)", "AWS Database", "db.r6g.xlarge / 500GB NVMe", 2, 85000, "=E3*F3", "プライマリ & スタンバイ構成"],
        [3, "Elasticache Redis クラスター", "AWS Cache", "cache.m6g.large (2ノード)", 2, 28000, "=E4*F4", "セッション & TMキャッシュ"],
        [4, "Application Load Balancer", "AWS Network", "冗長化構成", 2, 12000, "=E5*F5", "SSL終端 & WAF連携"],
        [5, "AI Cloud API クォータ利用料", "Gemini / Groq", "Pro tier (2M TPM)", 1, 150000, "=E6*F6", "月間翻訳トークン枠"],
        [6, "S3 Cloud Storage & Data Backup", "AWS Storage", "Glacier Deep Archive 2TB", 1, 18000, "=E7*F7", "日次バックアップ保存"]
    ]
    for r in items1:
        ws1.append(r)

    ws1.append(["合計 (Total)", "", "", "", "=SUM(E2:E7)", "", "=SUM(G2:G7)", "税抜月額合計"])
    ws1.append(["年間想定コスト (Annual Cost)", "", "", "", "", "", "=G8*12", "年額概算 (12ヶ月)"])

    # Sheet 2: Development Resource Estimates
    ws2 = wb.create_sheet(title="Dev_Estimates (工数見積)")
    headers2 = ["WBS ID", "開発タスク名 (Task Name)", "担当ロール", "工数 [人月]", "単価 [万円/人月]", "合計金額 [万円]", "進捗ステータス"]
    ws2.append(headers2)

    items2 = [
        ["WBS-101", "認証要件定義およびBrSE設計レビュー", "Lead BrSE", 1.5, 60, "=D2*E2", "完了"],
        ["WBS-102", "OAuth2/PKCE バックエンドAPI実装", "Senior Backend Dev", 2.5, 50, "=D3*E3", "進行中"],
        ["WBS-103", "管理画面UIおよび設定画面開発", "Frontend Dev", 2.0, 45, "=D4*E4", "進行中"],
        ["WBS-104", "結合テスト・負荷テスト・セキュリティ診断", "QA / Sec Engineer", 2.0, 45, "=D5*E5", "未着手"],
        ["WBS-105", "多言語用語集 (Glossary) 整備とAIファインチューニング", "AI Comtor", 1.0, 40, "=D6*E6", "未着手"]
    ]
    for r in items2:
        ws2.append(r)

    ws2.append(["総合計 (Grand Total)", "", "", "=SUM(D2:D6)", "", "=SUM(F2:F6)", "プロジェクト開発総額"])
    ws2.append(["平均人月単価 (Average Rate)", "", "", "", "=AVERAGE(E2:E6)", "", "平均単価"])

    # Style Sheet 1
    for cell in ws1[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0369A1")
        cell.alignment = Alignment(horizontal="center")
    for cell in ws2[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="047857")
        cell.alignment = Alignment(horizontal="center")

    # Add image to Sheet 1
    if os.path.exists(chart_img_path):
        try:
            img = OpenpyxlImage(chart_img_path)
            img.width = 580
            img.height = 290
            ws1.add_image(img, "B11")
        except Exception as e:
            print(f"Could not attach image to excel: {e}")

    out_path = os.path.join(OUTPUT_DIR, "02_BangDuToan_ChiPhi_Cloud_JA.xlsx")
    wb.save(out_path)
    print(f"Created XLSX at {out_path}")

# 3. PPTX (Google Slides)
def create_sample_pptx(arch_img_path: str):
    prs = pptx.Presentation()

    # Slide 1: Title Slide
    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "次世代マイクロサービス基盤 提案書"
    subtitle = slide1.placeholders[1]
    subtitle.text = "2026年度 クラウドネイティブ移行および自動翻訳コパイロット刷新計画\n発表者: BrSE 兼 アーキテクチャチーム"

    # Slide 2: Architecture & Diagram + Speaker Notes
    slide2 = prs.slides.add_slide(prs.slide_layouts[5]) # Title only layout
    slide2.shapes.title.text = "システム構成アーキテクチャ概要"
    
    # Add Image
    if os.path.exists(arch_img_path):
        slide2.shapes.add_picture(arch_img_path, PptxInches(1.0), PptxInches(1.8), width=PptxInches(8.0))

    # Add Speaker Notes
    notes2 = slide2.notes_slide.notes_text_frame
    notes2.text = "【発表者メモ】本スライドではAPI Gatewayを境界としたセキュリティ分離を強調してください。顧客データはVPC内でのみ復号されるため、外部からの侵入リスクを最小限に抑制できます。"

    # Slide 3: Migration Steps & Benefits + Speaker Notes
    slide3 = prs.slides.add_slide(prs.slide_layouts[1])
    slide3.shapes.title.text = "移行フェーズおよび導入メリット"
    tf = slide3.shapes.placeholders[1].text_frame
    tf.text = "フェーズ1: 認証・ユーザー管理機能のマイクロサービス化 (2026年Q3)"
    p1 = tf.add_paragraph()
    p1.text = "フェーズ2: ドキュメント翻訳エンジンおよび用語集AIの統合 (2026年Q4)"
    p2 = tf.add_paragraph()
    p2.text = "フェーズ3: Slack / Google Workspace 連携によるリアルタイム業務自動化"
    p3 = tf.add_paragraph()
    p3.text = "期待効果: BrSEおよびComtorのドキュメント作成・翻訳工数を最大65%削減"

    notes3 = slide3.notes_slide.notes_text_frame
    notes3.text = "【発表者メモ】経営陣に対しては、工数削減効果65%の根拠として過去のPoC検証実績数値を提示して説明を行ってください。"

    out_path = os.path.join(OUTPUT_DIR, "03_DeXuat_KienTruc_Microservices_JA.pptx")
    prs.save(out_path)
    print(f"Created PPTX at {out_path}")

# 4. PDF
def create_sample_pdf(arch_img_path: str):
    doc = fitz.open()

    # Page 1: Policy text & table
    page1 = doc.new_page(width=595, height=842) # A4
    page1.insert_textbox(fitz.Rect(50, 40, 545, 80), "情報セキュリティおよびデータ保護方針書", fontsize=18, fontname="helv")
    page1.insert_textbox(fitz.Rect(50, 85, 545, 110), "文書管理番号: SEC-2026-POL-001 · 発効日: 2026年9月1日 · 承認者: CISO", fontsize=10, fontname="helv")

    body_text = """1. 適用範囲と基本方針
本方針は、当社が開発および運用するすべてのクラウドシステム、APIサービス、ならびに翻訳自動化プラットフォームに適用されます。顧客情報およびプロジェクト機密情報の機密性・完全性・可用性を確実に担保します。

2. 認証およびアクセス制御基準
- パスワードは英大文字、小文字、数字、記号を含む12文字以上とし、90日ごとの更新を推奨します。
- 本番環境への特権アクセスには多要素認証 (MFA) およびIPホワイトリスト制限を義務付けます。
- 不正アクセス試行が連続5回検知されたアカウントは自動的に30分間ロックされます。

3. データの暗号化および保護基準
- 通信経路上のデータ: すべてTLS 1.3により強力に暗号化して伝送されます。
- 保存データ (Data at Rest): データベースおよびバックアップストレージはAES-256規格により暗号化されます。
- AIプロバイダー連携時: 顧客の個人情報 (PII) は自動マスク処理を経てからAIエンジンに送信されます。
"""
    page1.insert_textbox(fitz.Rect(50, 120, 545, 450), body_text, fontsize=10, fontname="helv")

    # Insert image on Page 1 bottom or Page 2
    if os.path.exists(arch_img_path):
        page1.insert_textbox(fitz.Rect(50, 460, 545, 480), "【セキュリティ境界とネットワーク構成図】", fontsize=11, fontname="helv")
        img_rect = fitz.Rect(50, 490, 545, 780)
        page1.insert_image(img_rect, filename=arch_img_path)

    out_path = os.path.join(OUTPUT_DIR, "04_QuyTrinh_BaoMat_SecurityPolicy_JA.pdf")
    doc.save(out_path)
    print(f"Created PDF at {out_path}")

if __name__ == "__main__":
    arch_img = os.path.join(IMG_DIR, "architecture_diagram.png")
    cost_chart = os.path.join(IMG_DIR, "cost_breakdown_chart.png")

    create_architecture_diagram(arch_img)
    create_cost_chart_diagram(cost_chart)

    create_sample_docx(arch_img)
    create_sample_xlsx(cost_chart)
    create_sample_pptx(arch_img)
    create_sample_pdf(arch_img)
    print("All test documents generated successfully!")
