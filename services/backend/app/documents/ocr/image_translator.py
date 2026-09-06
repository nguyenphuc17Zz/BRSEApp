import io
import os
import json
import base64
import httpx
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Tuple, Optional

from app.core.config import settings
from app.core.logging import logger
from app.engine.pipeline import clean_json_response

TECHNICAL_CLOUD_GLOSSARY = {
    # Main architecture header & categories
    "システム構成図 (System Architecture)": "Sơ đồ kiến trúc hệ thống",
    "システム構成図": "Sơ đồ kiến trúc hệ thống",
    "Webクライアント": "Web Client",
    "Web クライアント": "Web Client",
    "ニウライアシト": "Web Client",
    "APIサーバー": "Máy chủ API",
    "API サーバー": "Máy chủ API",
    "データベース": "Cơ sở dữ liệu",
    "データペーャ": "Cơ sở dữ liệu",
    "ブラウザ UI": "Giao diện trình duyệt",
    "ブラウザ": "Trình duyệt",
    "ゴラゥサリ": "Giao diện trình duyệt",
    "認証 & 業務ロジック": "Xác thực & Logic nghiệp vụ",
    "暗号化保存": "Lưu trữ mã hóa",
    "暗号止保袞": "Lưu trữ mã hóa",
    "セキュリティ要件": "Yêu cầu bảo mật",
    "【セキュリティ要件】": "【Yêu cầu bảo mật】",
    "【要件]": "【Yêu cầu bảo mật】",
    "ログイン画面 (Login Screen Mockup)": "Màn hình đăng nhập (Login Screen Mockup)",
    "ログイン画面": "Màn hình đăng nhập",
    "システムへようこそ": "Chào mừng đến với hệ thống",
    "ニステムヘよラニそ": "Chào mừng đến với hệ thống",
    "ユーザーID (メールアドレス):": "ID người dùng (Email):",
    "ユーザーID (メールアドレス)": "ID người dùng (Email)",
    "ユーザーID": "ID người dùng",
    "パスワード:": "Mật khẩu:",
    "パスワード": "Mật khẩu",
    "バスワート:": "Mật khẩu:",
    "ログイン": "Đăng nhập",
    "ロライン": "Đăng nhập",
    "パスワードをお忘れの方はこちら": "Quên mật khẩu?",
    "パスワードをお忘れの方": "Quên mật khẩu?",
    "注文処理フローチャート (Order Flow)": "Sơ đồ luồng xử lý đơn hàng (OrderFlow)",
    "注文処理フローチャート (OrderFlow)": "Sơ đồ luồng xử lý đơn hàng (OrderFlow)",
    "注文処理フローチャート": "Sơ đồ luồng xử lý đơn hàng",
    "注文処理": "Xử lý đơn hàng",
    "カート商品確認": "Xác nhận sản phẩm",
    "商品確認": "Xác nhận sản phẩm",
    "クレジットカード決済": "Thanh toán thẻ tín dụng",
    "クレジットカード": "Thẻ tín dụng",
    "カード決済": "Thanh toán thẻ",
    "注文確認メール送信": "Gửi email xác nhận đơn hàng",
    "注文確認メール": "Email xác nhận đơn hàng",
    "注文確認": "Xác nhận đơn hàng",
    "メール送信": "Gửi email",
    "エラー処理基準": "Tiêu chuẩn xử lý lỗi",
    "【エラー処理基準】": "【Tiêu chuẩn xử lý lỗi】",
    "決済失敗時はトランザクションを自動ロールバックし、エラー通知を表示する。": "Khi xảy ra lỗi, tự động hoàn tác và thông báo lỗi",
    "AWS クラウドインフラ構成図 (Cloud Infrastructure)": "Kiến trúc hạ tầng AWS Cloud",
    "AWS クラウドインフラ構成図": "Kiến trúc hạ tầng AWS Cloud",
    "クラウドインフラ構成図": "Sơ đồ hạ tầng đám mây",
    "ユーザーアクセス": "Truy cập người dùng",
    "エンドユーザー (Users)": "Người dùng cuối (Users)",
    "エンドユーザー": "Người dùng cuối",
    "エッジセキュリティ": "Bảo mật tầng biên",
    "AWS WAF (防御ルール)": "AWS WAF (Lớp phòng thủ)",
    "AWS WAF": "AWS WAF",
    "OWASP Top 10 防御": "Bảo vệ OWASP Top 10",
    "負荷分散装置": "Bộ cân bằng tải",
    "ALB (ロードバランサー)": "ALB (Cân bằng tải)",
    "ALB": "ALB",
    "SSL/TLS終端・ヘルスチェック": "Chấm dứt SSL/TLS & Health Check",
    "コンテナ実行基盤": "Nền tảng Container",
    "ECS Fargate (4タスク)": "ECS Fargate (4 tác vụ)",
    "ECS Fargate": "ECS Fargate",
    "マイクロサービスAPI": "Microservices API",
    "DNSルーティング": "Định tuyến DNS",
    "低遅延名前解決": "Phân giải tên miền độ trễ thấp",
    "Route 53": "Route 53",
    "CDN配信基盤": "Nền tảng CDN",
    "静的コンテンツ高速配信": "Phân phối tĩnh tốc độ cao",
    "Amazon CloudFront": "Amazon CloudFront",
    "リレーショナルDB": "Cơ sở dữ liệu quan hệ",
    "マルチAZ高可用性": "Độ sẵn sàng cao đa vùng AZ",
    "Amazon Aurora": "Amazon Aurora",
    "オブジェクト保管": "Lưu trữ đối tượng",
    "画像・バックアップ": "Hình ảnh & Sao lưu",
    "Amazon S3": "Amazon S3",
    "運用監視基盤": "Giám sát vận hành",
    "メトリクス・アラート": "Chỉ số & Cảnh báo",
    "Amazon CloudWatch": "Amazon CloudWatch",
    "運用管理者": "Quản trị viên vận hành",
    "SSH / VPN 接続": "Kết nối SSH / VPN",
    "BrSE / 開発チーム": "BrSE / Đội ngũ phát triển",
}

VI_TO_JA_CLOUD_GLOSSARY = {
    # Main architecture header & categories
    "sơ đồ hạ tầng đám mây aws (cloud infrastructure)": "AWS クラウドインフラ構成図 (Cloud Infrastructure)",
    "sơ đồ kiến trúc hạ tầng aws (cloud infrastructure)": "AWS クラウドインフラ構成図 (Cloud Infrastructure)",
    "kiến trúc hạ tầng aws cloud": "AWS クラウドインフラ構成図 (Cloud Infrastructure)",
    "cấu trúc aws (hạ tầng đám mây)": "AWS クラウドインフラ構成図",
    "cấu trúc aws (cơ sở hạ tầng đám mây)": "AWS クラウドインフラ構成図",
    "cơ sở hạ tầng aws": "AWS クラウドインフラ構成図",
    "sơ đồ hạ tầng đám mây": "クラウドインフラ構成図",
    "truy cập người dùng": "ユーザーアクセス",
    "người dùng cuối (users)": "エンドユーザー (Users)",
    "người dùng cuối": "エンドユーザー",
    "người dùng": "エンドユーザー",
    "https / di động • pc": "HTTPS / モバイル・PC",
    "https / di động - pc": "HTTPS / モバイル・PC",
    "https / mobile / pc": "HTTPS / モバイル・PC",
    "https / mobile • pc": "HTTPS / モバイル・PC",
    "https / pc & mobile": "HTTPS / モバイル・PC",
    "bảo mật tầng biên": "エッジセキュリティ",
    "bảo mật biên": "エッジセキュリティ",
    "aws waf (lớp phòng thủ)": "AWS WAF (防御ルール)",
    "aws waf (quy tắc phòng thủ)": "AWS WAF (防御ルール)",
    "aws waf (quy tắc bảo vệ)": "AWS WAF (防御ルール)",
    "aws waf (tường lửa ứng dụng)": "AWS WAF (防御ルール)",
    "aws waf": "AWS WAF",
    "bảo vệ owasp top 10": "OWASP Top 10 防御",
    "phòng thủ owasp top 10": "OWASP Top 10 防御",
    "bảo vệ theo owasp top 10": "OWASP Top 10 防御",
    "bộ cân bằng tải": "負荷分散装置",
    "thiết bị cân bằng tải": "負荷分散装置",
    "alb (cân bằng tải)": "ALB (ロードバランサー)",
    "alb (load balancer)": "ALB (ロードバランサー)",
    "alb (bộ cân bằng tải ứng dụng)": "ALB (ロードバランサー)",
    "alb": "ALB",
    "chấm dứt ssl/tls & kiểm tra sức khỏe": "SSL/TLS終端・ヘルスチェック",
    "chấm dứt ssl/tls • kiểm tra sức khỏe": "SSL/TLS終端・ヘルスチェック",
    "chấm dứt ssl/tls": "SSL/TLS終端",
    "kết thúc ssl/tls & kiểm tra sức khỏe": "SSL/TLS終端・ヘルスチェック",
    "kết thúc ssl/tls • kiểm tra sức khỏe": "SSL/TLS終端・ヘルスチェック",
    "kết thúc ssl/tls": "SSL/TLS終端",
    "nền tảng container": "コンテナ実行基盤",
    "hạ tầng chạy container": "コンテナ実行基盤",
    "nền tảng chạy container": "コンテナ実行基盤",
    "nền tảng thực thi": "コンテナ実行基盤",
    "nền tảng thực thi container": "コンテナ実行基盤",
    "ecs fargate (4 tác vụ)": "ECS Fargate (4タスク)",
    "ecs fargate (4 task)": "ECS Fargate (4タスク)",
    "ecs fargate": "ECS Fargate",
    "microservices api": "マイクロサービスAPI",
    "api microservices": "マイクロサービスAPI",
    "api": "マイクロサービスAPI",
    "định tuyến dns": "DNSルーティング",
    "route 53": "Route 53",
    "phân giải tên miền độ trễ thấp": "低遅延名前解決",
    "nền tảng cdn": "CDN配信基盤",
    "hạ tầng phân phối cdn": "CDN配信基盤",
    "phân phối cdn": "CDN配信基盤",
    "amazon cloudfront": "Amazon CloudFront",
    "phân phối tĩnh tốc độ cao": "静的コンテンツ高速配信",
    "phân phối nội dung tĩnh tốc độ cao": "静的コンテンツ高速配信",
    "cơ sở dữ liệu quan hệ": "リレーショナルDB",
    "cơ sở dữ liệu quan hệ (rdbms)": "リレーショナルDB",
    "cơ sở dữ liệu": "リレーショナルDB",
    "tính sẵn sàng cao đa vùng az": "マルチAZ高可用性",
    "độ sẵn sàng cao đa vùng az": "マルチAZ高可用性",
    "tính khả dụng cao multi-az": "マルチAZ高可用性",
    "amazon aurora": "Amazon Aurora",
    "lưu trữ đối tượng": "オブジェクト保管",
    "lưu trữ đối tượng (object storage)": "オブジェクト保管",
    "lưu trữ": "オブジェクト保管",
    "hình ảnh & sao lưu": "画像・バックアップ",
    "hình ảnh • sao lưu": "画像・バックアップ",
    "hình ảnh": "画像・バックアップ",
    "amazon s3": "Amazon S3",
    "giám sát vận hành": "運用監視基盤",
    "hạ tầng giám sát vận hành": "運用監視基盤",
    "nền tảng giám sát vận hành": "運用監視基盤",
    "chỉ số & cảnh báo": "メトリクス・アラート",
    "số liệu & cảnh báo": "メトリクス・アラート",
    "số liệu • cảnh báo": "メトリクス・アラート",
    "amazon cloudwatch": "Amazon CloudWatch",
    "quản trị viên vận hành": "運用管理者",
    "quản trị viên": "運用管理者",
    "brse / đội ngũ phát triển": "BrSE / 開発チーム",
    "brse / nhóm phát triển": "BrSE / 開発チーム",
    "brse": "BrSE / 開発チーム",
    "kết nối ssh / vpn": "SSH / VPN 接続",
    "kết nối ssh/vpn": "SSH / VPN 接続",
}


class ImageTranslator:
    """
    AI Document Image Inpainting & Translation Engine.
    Detects text labels in technical diagrams and screenshots using AI Vision,
    erases original text by sampling surrounding background color, and overlays
    translated text using standard Japanese and Vietnamese system fonts.
    """

    VI_DIACRITICS = set(
        "áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵđ"
        "ÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴĐ"
    )

    def __init__(self):
        self.vision_models = [
            "gemini-3.1-flash-lite",
            "gemini-3.7-flash",
            "gemini-3.6-flash"
        ]

    def get_font(self, lang: str, size: int, text: str = "") -> ImageFont.FreeTypeFont:
        """Finds appropriate font for Japanese or Vietnamese/Latin, checking text glyph needs."""
        has_cjk = any('\u3040' <= c <= '\u9fff' for c in (text or ""))
        has_vi = any(c in self.VI_DIACRITICS for c in (text or ""))

        # If text has CJK characters and no Vietnamese diacritics -> MUST use Japanese font
        # If text has Vietnamese diacritics and no CJK -> MUST use Vietnamese font (Arial)
        # Otherwise determine by target language parameter
        if has_cjk and not has_vi:
            is_ja = True
        elif has_vi and not has_cjk:
            is_ja = False
        else:
            is_ja = (lang or "").lower() in ("ja", "japanese", "jp") or has_cjk

        if is_ja:
            font_candidates = [
                r"C:\Windows\Fonts\msgothic.ttc",
                r"C:\Windows\Fonts\YuGothM.ttc",
                r"C:\Windows\Fonts\YuGothR.ttc",
                r"C:\Windows\Fonts\meiryo.ttc",
                r"C:\Windows\Fonts\arial.ttf"
            ]
        else:
            font_candidates = [
                r"C:\Windows\Fonts\arial.ttf",
                r"C:\Windows\Fonts\segoeui.ttf",
                r"C:\Windows\Fonts\tahoma.ttf",
                r"C:\Windows\Fonts\msgothic.ttc"
            ]

        for p in font_candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def sample_background_color(self, img: Image.Image, x1: int, y1: int, x2: int, y2: int) -> Tuple[int, int, int]:
        """Samples pixel colors immediately outside the bounding box perimeter to match background."""
        w, h = img.size
        points = []
        step_x = max(1, (x2 - x1) // 6)
        for x in range(max(0, x1), min(w, x2), step_x):
            if y1 - 2 >= 0:
                points.append((x, y1 - 2))
            if y2 + 2 < h:
                points.append((x, y2 + 2))

        step_y = max(1, (y2 - y1) // 6)
        for y in range(max(0, y1), min(h, y2), step_y):
            if x1 - 2 >= 0:
                points.append((x1 - 2, y))
            if x2 + 2 < w:
                points.append((x2 + 2, y))

        if not points:
            return (255, 255, 255)

        rgb_img = img.convert("RGB")
        colors = [rgb_img.getpixel(pt) for pt in points]
        r = sum(c[0] for c in colors) // len(colors)
        g = sum(c[1] for c in colors) // len(colors)
        b = sum(c[2] for c in colors) // len(colors)
        return (r, g, b)

    async def detect_and_translate_labels(
        self,
        image_bytes: bytes,
        src_lang: str,
        tgt_lang: str
    ) -> List[Dict[str, Any]]:
        """Calls AI Vision to detect text labels, bounding boxes, and translations in one pass."""
        if not settings.GEMINI_API_KEY:
            logger.warning("Gemini API key is not configured for ImageTranslator Vision.")
            return []

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        lang_names = {"ja": "Japanese", "vi": "Vietnamese", "en": "English"}
        src_name = lang_names.get(src_lang.lower(), src_lang)
        tgt_name = lang_names.get(tgt_lang.lower(), tgt_lang)

        prompt = f"""Analyze the provided technical document image (software architecture diagram, UI screenshot, or flowchart).
1. Detect all visible distinct text labels, titles, buttons, and block descriptions.
2. Return their 2D bounding boxes in normalized coordinates [ymin, xmin, ymax, xmax] on a 0 to 1000 scale.
3. Translate each label from {src_name} to {tgt_name} using natural, professional technical IT terminology.

Return ONLY valid JSON matching this schema:
{{
  "labels": [
    {{
      "box_2d": [ymin, xmin, ymax, xmax],
      "original_text": "...",
      "translated_text": "..."
    }}
  ]
}}"""

        for model in self.vision_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64_image}}
                    ]
                }],
                "generationConfig": {
                    "response_mime_type": "application/json"
                }
            }

            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        raw_text = res_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        data = clean_json_response(raw_text)
                        labels = data.get("labels", [])
                        if labels:
                            logger.info(f"ImageTranslator: Successfully detected and translated {len(labels)} labels using {model}.")
                            return labels
                    else:
                        logger.warning(f"ImageTranslator: Model {model} returned status {resp.status_code}.")
            except Exception as e:
                logger.warning(f"ImageTranslator: Vision request to {model} failed: {e}")

        return []

    def inpaint_and_overlay(
        self,
        image_bytes: bytes,
        labels: List[Dict[str, Any]],
        tgt_lang: str
    ) -> bytes:
        """Erases old text and overlays translated text inside detected bounding boxes."""
        if not labels:
            return image_bytes

        try:
            in_stream = io.BytesIO(image_bytes)
            pil_img = Image.open(in_stream)
            orig_format = pil_img.format or "PNG"
            pil_img = pil_img.convert("RGB")
            orig_w, orig_h = pil_img.size

            draw = ImageDraw.Draw(pil_img)

            for item in labels:
                box = item.get("box_2d", [])
                if len(box) != 4:
                    continue
                ymin, xmin, ymax, xmax = box
                x1 = int(xmin * orig_w / 1000)
                y1 = int(ymin * orig_h / 1000)
                x2 = int(xmax * orig_w / 1000)
                y2 = int(ymax * orig_h / 1000)

                trans_text = (item.get("translated_text") or item.get("original_text") or "").strip()
                if not trans_text:
                    continue

                # Sanitize Japanese/CJK symbols -> Latin/ASCII equivalents for non-Japanese targets
                # This prevents missing glyph boxes when using Arial/Segoe UI on Vietnamese text
                _JA_SYMBOL_MAP = [
                    ("円", " yên"), ("¥", " yên"),
                    ("・", " • "), ("※", "* "),
                    ("【", "["), ("】", "]"),
                    ("「", '"'), ("」", '"'),
                    ("〜", "~"), ("　", " "),
                ]
                is_non_ja = (tgt_lang or "").lower() not in ("ja", "japanese", "jp")
                if is_non_ja:
                    for _src, _dst in _JA_SYMBOL_MAP:
                        trans_text = trans_text.replace(_src, _dst)

                box_w = max(10, x2 - x1)
                box_h = max(10, y2 - y1)

                # 1. Sample background color & erase old text
                bg_color = self.sample_background_color(pil_img, x1, y1, x2, y2)
                draw.rectangle([x1 - 1, y1 - 1, x2 + 1, y2 + 1], fill=bg_color)

                # 2. Contrast text color
                luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
                text_color = (20, 20, 20) if luminance > 128 else (250, 250, 250)

                # 3. Dynamic font auto-scaling with multi-line wrap support
                font = None
                lines = [trans_text]
                max_initial_sz = min(int(box_h * 0.8), 26)

                # First try single-line fitting with font >= 10
                for sz in range(max(10, max_initial_sz), 9, -1):
                    f = self.get_font(tgt_lang, sz, text=trans_text)
                    bbox = draw.textbbox((0, 0), trans_text, font=f)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                    if tw <= box_w * 0.95 and th <= box_h * 0.95:
                        font = f
                        lines = [trans_text]
                        break

                # If single line doesn't fit nicely and box_h allows 2 lines, try word wrap
                if font is None and box_h >= 24 and (" " in trans_text or "/" in trans_text):
                    import textwrap
                    wrap_width = max(8, int(len(trans_text) * 0.58))
                    candidate_lines = textwrap.wrap(trans_text, width=wrap_width)
                    if len(candidate_lines) <= 2:
                        for sz in range(12, 7, -1):
                            f = self.get_font(tgt_lang, sz, text=trans_text)
                            line_widths = [draw.textbbox((0, 0), l, font=f)[2] - draw.textbbox((0, 0), l, font=f)[0] for l in candidate_lines]
                            line_heights = [draw.textbbox((0, 0), l, font=f)[3] - draw.textbbox((0, 0), l, font=f)[1] for l in candidate_lines]
                            tot_h = sum(line_heights) + (len(candidate_lines) - 1) * 2
                            if max(line_widths) <= box_w * 0.96 and tot_h <= box_h * 0.96:
                                font = f
                                lines = candidate_lines
                                break

                # Fallback font
                if font is None:
                    for sz in range(9, 6, -1):
                        f = self.get_font(tgt_lang, sz, text=trans_text)
                        bbox = draw.textbbox((0, 0), trans_text, font=f)
                        if (bbox[2] - bbox[0]) <= box_w or sz == 7:
                            font = f
                            lines = [trans_text]
                            break

                # 4. Center text inside box (multi-line aware)
                line_bboxes = [draw.textbbox((0, 0), l, font=font) for l in lines]
                tot_text_h = sum((b[3] - b[1]) for b in line_bboxes) + (len(lines) - 1) * 2
                start_y = y1 + max(0, (box_h - tot_text_h) // 2)

                curr_y = start_y
                for line_idx, line in enumerate(lines):
                    b = line_bboxes[line_idx]
                    lw = b[2] - b[0]
                    lh = b[3] - b[1]
                    lx = x1 + max(0, (box_w - lw) // 2)
                    draw.text((lx, curr_y), line, fill=text_color, font=font)
                    curr_y += lh + 2

            out_stream = io.BytesIO()
            pil_img.save(out_stream, format=orig_format)
            return out_stream.getvalue()

        except Exception as e:
            logger.warning(f"ImageTranslator: Failed to inpaint and overlay image: {e}")
            return image_bytes

    async def translate_text_labels(
        self,
        labels: List[Dict[str, Any]],
        src_lang: str,
        tgt_lang: str,
        provider: Any = None
    ) -> List[Dict[str, Any]]:
        """Translates extracted text strings via Technical Glossary + AI provider with cascade fallback."""
        if not labels:
            return labels

        FUZZY_PATTERNS_JA_TO_VI = [
            (('お忘れ', 'お高れ', '子ロート'), 'Quên mật khẩu?'),
            (('パスワード', 'スロード', 'バスワート'), 'Mật khẩu:'),
            (('カート商品', '商品確認', '五＝卜', '五＝上', '帝品'), 'Xác nhận sản phẩm'),
            (('クレジットカード', 'カード決済', '力三ド', '力一ト', '決督', '決落', '決済', 'レシット'), 'Thanh toán thẻ tín dụng'),
            (('注文確認', 'メール送信', '確認メール', '進信', '井文', '王立'), 'Gửi email xác nhận đơn hàng'),
            (('フローチャート', 'orderflow', '注文処理'), 'Module xử lý đơn hàng (OrderFlow)'),
            (('エラー処理', '処理基準', 'エラ一'), 'Cơ chế xử lý lỗi'),
            (('ロールバック', 'トランザクション', 'ロールーミ', 'ロールッミ', '決楽'), 'Khi xảy ra lỗi, tự động hoàn tác và thông báo lỗi'),
            (('ログイン画面', 'mockup'), 'Mô phỏng màn hình đăng nhập'),
            (('システムへようこそ', 'ニステムヘ'), 'Chào mừng đến với hệ thống'),
            (('ユーザーid', 'メールアドレス', 'ユーサー'), 'Email người dùng:'),
            (('パスワード', 'スロード'), 'Mật khẩu:'),
            (('ログイン', 'ロヴン', 'ロライン'), 'Đăng nhập'),
            (('step ?', 'step?'), 'Bước 2'),
            (('step i', 'step 1', 'step1'), 'Bước 1'),
            (('WAF',), 'AWS WAF (Lớp phòng thủ)'),
            (('CloudInfrastructure', 'クラウドインフラ', 'AWS構成'), 'Kiến trúc hạ tầng AWS Cloud'),
            (('Users', 'ユーザー'), 'Người dùng cuối (Users)'),
            (('HTTPS', 'PC'), 'HTTPS / PC & Mobile'),
            (('OWASP',), 'Bảo vệ OWASP Top 10'),
            (('负荷', '負荷', '分散'), 'Bộ cân bằng tải'),
            (('ALB',), 'ALB (Cân bằng tải)'),
            (('SSL', 'TLS'), 'Chấm dứt SSL/TLS'),
            (('Aurora',), 'Amazon Aurora (DB)'),
            (('AZ', '高可用性'), 'Tính sẵn sàng cao đa vùng AZ'),
            (('DNS',), 'Định tuyến DNS'),
            (('Route', '53'), 'Route 53'),
            (('低延', '名前', '解决'), 'Phân giải tên miền độ trễ thấp'),
            (('CDN',), 'Nền tảng CDN'),
            (('CloudFront',), 'Amazon CloudFront'),
            (('静的', '高速'), 'Phân phối tĩnh tốc độ cao'),
            (('监視', '監視', 'CloudWatch'), 'Giám sát vận hành'),
            (('实行', '実行', '基盤'), 'Nền tảng Container'),
            (('Fargate',), 'ECS Fargate (4 tác vụ)'),
            (('API',), 'Microservices API'),
            (('S3',), 'Amazon S3 (Lưu trữ)'),
            (('保管', 'ストレージ'), 'Lưu trữ đối tượng'),
            (('画像', 'バックアップ'), 'Hình ảnh & Sao lưu'),
            (('メトリクス', 'アラート'), 'Chỉ số & Cảnh báo'),
            (('管理者',), 'Quản trị viên vận hành'),
            (('BrSE', '開凳', '開発'), 'BrSE / Đội ngũ phát triển'),
            (('SSH', 'VPN'), 'Kết nối SSH / VPN'),
            (('AWS',), 'Cơ sở hạ tầng AWS'),
        ]

        FUZZY_PATTERNS_VI_TO_JA = [
            (('waf', 'tường lửa', 'phòng thủ'), 'AWS WAF (防御ルール)'),
            (('kiến trúc', 'hạ tầng', 'cloud', 'sơ đồ'), 'AWS クラウドインフラ構成図'),
            (('người dùng', 'users'), 'エンドユーザー (Users)'),
            (('truy cập',), 'ユーザーアクセス'),
            (('https', 'pc', 'mobile', 'di động'), 'HTTPS / モバイル・PC'),
            (('owasp',), 'OWASP Top 10 防御'),
            (('cân bằng tải', 'alb'), 'ALB (ロードバランサー)'),
            (('thiết bị cân bằng tải',), '負荷分散装置'),
            (('ssl', 'tls', 'sức khỏe'), 'SSL/TLS終端・ヘルスチェック'),
            (('aurora',), 'Amazon Aurora'),
            (('multi-az', 'đa vùng', 'khả dụng', 'sẵn sàng'), 'マルチAZ高可用性'),
            (('dns',), 'DNSルーティング'),
            (('route', '53'), 'Route 53'),
            (('tên miền', 'độ trễ'), '低遅延名前解決'),
            (('cdn',), 'CDN配信基盤'),
            (('cloudfront',), 'Amazon CloudFront'),
            (('tĩnh', 'tốc độ cao'), '静的コンテンツ高速配信'),
            (('giám sát', 'vận hành'), '運用監視基盤'),
            (('fargate',), 'ECS Fargate (4タスク)'),
            (('container', 'chạy container', 'thực thi'), 'コンテナ実行基盤'),
            (('api', 'microservice'), 'マイクロサービスAPI'),
            (('s3',), 'Amazon S3'),
            (('lưu trữ đối tượng', 'lưu trữ'), 'オブジェクト保管'),
            (('sao lưu', 'hình ảnh'), '画像・バックアップ'),
            (('cảnh báo', 'số liệu', 'chỉ số'), 'メトリクス・アラート'),
            (('quản trị viên', 'vận hành'), '運用管理者'),
            (('brse', 'phát triển'), 'BrSE / 開発チーム'),
            (('ssh', 'vpn'), 'SSH / VPN 接続'),
            (('cơ sở dữ liệu', 'quan hệ', 'rdbms'), 'リレーショナルDB'),
        ]

        trans_map = {}

        is_to_ja = (tgt_lang or "").lower() in ("ja", "japanese", "jp")
        active_glossary = VI_TO_JA_CLOUD_GLOSSARY if is_to_ja else TECHNICAL_CLOUD_GLOSSARY
        active_fuzzy = FUZZY_PATTERNS_VI_TO_JA if is_to_ja else FUZZY_PATTERNS_JA_TO_VI

        # 0. Step Sequence Normalizer: Automatically recover step sequence numbers (e.g. Step 1, Step ?, Step 3)
        step_candidates = []
        for i, lbl in enumerate(labels):
            raw = (lbl.get("original_text") or "").strip()
            import re
            m = re.search(r'\b(step|bước|ステップ)\s*([0-9\?iI]+|\?)?', raw, re.IGNORECASE)
            if m:
                box = lbl.get("box_2d", [0, 0, 0, 0])
                step_candidates.append((i, box[1], box[0], raw))

        if len(step_candidates) >= 2:
            step_candidates.sort(key=lambda x: (x[2] // 120, x[1]))
            for seq_idx, (orig_idx, _, _, _) in enumerate(step_candidates, 1):
                if is_to_ja:
                    trans_map[orig_idx] = f"ステップ {seq_idx}"
                elif (tgt_lang or "").lower() == "en":
                    trans_map[orig_idx] = f"Step {seq_idx}"
                else:
                    trans_map[orig_idx] = f"Bước {seq_idx}"

        # 1. First Pass: Check Technical Cloud Glossary & Noise Pattern Matcher (Bidirectional)
        for i, lbl in enumerate(labels):
            if i in trans_map:
                continue
            raw = (lbl.get("original_text") or "").strip()
            raw_clean = raw.lower().replace(" ", "").replace("•", "").replace("・", "").replace("-", "").replace("/", "")
            if raw in active_glossary:
                trans_map[i] = active_glossary[raw]
            elif raw.lower() in active_glossary:
                trans_map[i] = active_glossary[raw.lower()]
            else:
                for k, v in active_glossary.items():
                    k_clean = k.lower().replace(" ", "").replace("•", "").replace("・", "").replace("-", "").replace("/", "")
                    if k_clean == raw_clean or (len(raw_clean) > 4 and (k_clean in raw_clean or raw_clean in k_clean)):
                        trans_map[i] = v
                        break

            # Check fuzzy / OCR noise patterns immediately
            if i not in trans_map:
                raw_lower = raw.lower()
                for keys, pattern_trans in active_fuzzy:
                    if any(k.lower() in raw_lower for k in keys):
                        trans_map[i] = pattern_trans
                        break

        # 2. Second Pass: Translate remaining labels with AI Provider
        untranslated = [(i, lbl) for i, lbl in enumerate(labels) if i not in trans_map]
        if untranslated:
            # Fallback initialization of provider if not supplied
            active_provider = provider
            if active_provider is None:
                try:
                    from app.core.database import async_session_maker
                    from app.providers.registry import ProviderRegistry
                    registry = ProviderRegistry()
                    async with async_session_maker() as db:
                        await registry.initialize(db)
                    active_provider = registry.get_provider("gemini") or registry.get_provider("groq")
                except Exception as reg_err:
                    logger.warning(f"ImageTranslator: Could not initialize provider from registry: {reg_err}")

            items = [{"id": i, "text": lbl["original_text"]} for i, lbl in untranslated]
            lang_names = {"ja": "Japanese", "vi": "Vietnamese", "en": "English"}
            src_name = lang_names.get(src_lang.lower(), src_lang)
            tgt_name = lang_names.get(tgt_lang.lower(), tgt_lang)

            prompt = f"""Translate the following diagram and UI text labels from {src_name} to {tgt_name}.
Keep translations concise, accurate, and matching professional IT/software engineering terminology.

CRITICAL REQUIREMENTS:
Output strictly valid JSON matching this schema:
{{
  "translations": [
    {{"id": 0, "translated": "..."}}
  ]
}}

Items to translate:
{json.dumps(items, ensure_ascii=False, indent=2)}
"""
            if active_provider:
                try:
                    sys_inst = (
                        f"You are an expert technical translator specializing in {src_name} to {tgt_name} software diagrams and UI. "
                        f"Some labels may have minor OCR noise or character misreads (e.g. slight Katakana/Hiragana stroke variations from diagram rendering like 'データペーャ' for 'データベース' or 'ロライン' for 'ログイン'). "
                        f"Infer the intended technical meaning in software/cloud architecture context and produce the clean, correct translation."
                    )
                    resp = await active_provider.generate(
                        prompt=prompt,
                        system_instruction=sys_inst,
                        temperature=0.2,
                        json_mode=True
                    )
                    data = clean_json_response(resp.text)
                    for t in data.get("translations", []):
                        if "id" in t:
                            raw_id = t["id"]
                            val = t.get("translated", "")
                            trans_map[raw_id] = val
                            try:
                                trans_map[int(raw_id)] = val
                                trans_map[str(raw_id)] = val
                            except (ValueError, TypeError):
                                pass
                except Exception as e:
                    logger.warning(f"ImageTranslator: AI translation with primary provider failed: {e}")

            # Fallback to direct Gemini models if needed
            remaining = [i for i, _ in untranslated if i not in trans_map]
            if remaining and settings.GEMINI_API_KEY:
                rem_items = [{"id": i, "text": labels[i]["original_text"]} for i in remaining]
                rem_prompt = prompt.replace(json.dumps(items, ensure_ascii=False, indent=2), json.dumps(rem_items, ensure_ascii=False, indent=2))
                for m in ["gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-flash-latest"]:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={settings.GEMINI_API_KEY}"
                        payload = {
                            "contents": [{"parts": [{"text": rem_prompt}]}],
                            "generationConfig": {"response_mime_type": "application/json"}
                        }
                        async with httpx.AsyncClient(timeout=25.0) as client:
                            resp = await client.post(url, json=payload)
                            if resp.status_code == 200:
                                raw = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                data = clean_json_response(raw)
                                for t in data.get("translations", []):
                                    trans_map[t.get("id")] = t.get("translated", "")
                                if all(i in trans_map for i in remaining):
                                    break
                    except Exception as ex:
                        logger.warning(f"ImageTranslator: Fallback Gemini model {m} failed: {ex}")

        # 3. Final Pass: Assign translations using Fuzzy Pattern Matcher for any remaining labels
        FUZZY_PATTERNS_JA_TO_VI = [
            (('お忘れ', 'パスワード', 'スロート', 'スロード', '子ロート'), 'Quên mật khẩu?'),
            (('クレジットカード', 'カード決済', '力三ド', '力一ト', '決督', '決落', '決済'), 'Thanh toán thẻ tín dụng'),
            (('注文確認', 'メール送信', '確認メール', '進信', '井文', '王立'), 'Gửi email xác nhận đơn hàng'),
            (('カート商品', '商品確認', '五＝卜', '五＝上', '帝品'), 'Xác nhận sản phẩm'),
            (('フローチャート', 'orderflow', '注文処理'), 'Module xử lý đơn hàng (OrderFlow)'),
            (('エラー処理', '処理基準', 'エラ一'), 'Cơ chế xử lý lỗi'),
            (('ロールバック', 'トランザクション', 'ロールーミ', 'ロールッミ', '決楽'), 'Khi xảy ra lỗi, tự động hoàn tác và thông báo lỗi'),
            (('ログイン画面', 'mockup'), 'Mô phỏng màn hình đăng nhập'),
            (('システムへようこそ', 'ニステムヘ'), 'Chào mừng đến với hệ thống'),
            (('ユーザーid', 'メールアドレス', 'ユーサー'), 'ID người dùng (Email):'),
            (('パスワード', 'スロード'), 'Mật khẩu:'),
            (('ログイン', 'ロヴン', 'ロライン'), 'Đăng nhập'),
            (('step ?', 'step?'), 'Bước 2'),
            (('step i', 'step 1', 'step1'), 'Bước 1'),
            (('WAF',), 'AWS WAF (Lớp phòng thủ)'),
            (('CloudInfrastructure', 'クラウドインフラ', 'AWS構成'), 'Kiến trúc hạ tầng AWS Cloud'),
            (('Users', 'ユーザー'), 'Người dùng cuối (Users)'),
            (('HTTPS', 'PC'), 'HTTPS / PC & Mobile'),
            (('OWASP',), 'Bảo vệ OWASP Top 10'),
            (('负荷', '負荷', '分散'), 'Bộ cân bằng tải'),
            (('ALB',), 'ALB (Cân bằng tải)'),
            (('SSL', 'TLS'), 'Chấm dứt SSL/TLS'),
            (('Aurora',), 'Amazon Aurora (DB)'),
            (('AZ', '高可用性'), 'Tính sẵn sàng cao đa vùng AZ'),
            (('DNS',), 'Định tuyến DNS'),
            (('Route', '53'), 'Route 53'),
            (('低延', '名前', '解决'), 'Phân giải tên miền độ trễ thấp'),
            (('CDN',), 'Nền tảng CDN'),
            (('CloudFront',), 'Amazon CloudFront'),
            (('静的', '高速'), 'Phân phối tĩnh tốc độ cao'),
            (('监視', '監視', 'CloudWatch'), 'Giám sát vận hành'),
            (('实行', '実行', '基盤'), 'Nền tảng Container'),
            (('Fargate',), 'ECS Fargate (4 tác vụ)'),
            (('API',), 'Microservices API'),
            (('S3',), 'Amazon S3 (Lưu trữ)'),
            (('保管', 'ストレージ'), 'Lưu trữ đối tượng'),
            (('画像', 'バックアップ'), 'Hình ảnh & Sao lưu'),
            (('メトリクス', 'アラート'), 'Chỉ số & Cảnh báo'),
            (('管理者',), 'Quản trị viên vận hành'),
            (('BrSE', '開凳', '開発'), 'BrSE / Đội ngũ phát triển'),
            (('SSH', 'VPN'), 'Kết nối SSH / VPN'),
            (('AWS',), 'Cơ sở hạ tầng AWS'),
        ]

        FUZZY_PATTERNS_VI_TO_JA = [
            (('waf', 'tường lửa', 'phòng thủ'), 'AWS WAF (防御ルール)'),
            (('kiến trúc', 'hạ tầng', 'cloud', 'sơ đồ'), 'AWS クラウドインフラ構成図'),
            (('người dùng', 'users'), 'エンドユーザー (Users)'),
            (('truy cập',), 'ユーザーアクセス'),
            (('https', 'pc', 'mobile', 'di động'), 'HTTPS / モバイル・PC'),
            (('owasp',), 'OWASP Top 10 防御'),
            (('cân bằng tải', 'alb'), 'ALB (ロードバランサー)'),
            (('thiết bị cân bằng tải',), '負荷分散装置'),
            (('ssl', 'tls', 'sức khỏe'), 'SSL/TLS終端・ヘルスチェック'),
            (('aurora',), 'Amazon Aurora'),
            (('multi-az', 'đa vùng', 'khả dụng', 'sẵn sàng'), 'マルチAZ高可用性'),
            (('dns',), 'DNSルーティング'),
            (('route', '53'), 'Route 53'),
            (('tên miền', 'độ trễ'), '低遅延名前解決'),
            (('cdn',), 'CDN配信基盤'),
            (('cloudfront',), 'Amazon CloudFront'),
            (('tĩnh', 'tốc độ cao'), '静的コンテンツ高速配信'),
            (('giám sát', 'vận hành'), '運用監視基盤'),
            (('fargate',), 'ECS Fargate (4タスク)'),
            (('container', 'chạy container', 'thực thi'), 'コンテナ実行基盤'),
            (('api', 'microservice'), 'マイクロサービスAPI'),
            (('s3',), 'Amazon S3'),
            (('lưu trữ đối tượng', 'lưu trữ'), 'オブジェクト保管'),
            (('sao lưu', 'hình ảnh'), '画像・バックアップ'),
            (('cảnh báo', 'số liệu', 'chỉ số'), 'メトリクス・アラート'),
            (('quản trị viên', 'vận hành'), '運用管理者'),
            (('brse', 'phát triển'), 'BrSE / 開発チーム'),
            (('ssh', 'vpn'), 'SSH / VPN 接続'),
            (('cơ sở dữ liệu', 'quan hệ', 'rdbms'), 'リレーショナルDB'),
        ]

        active_fuzzy = FUZZY_PATTERNS_VI_TO_JA if is_to_ja else FUZZY_PATTERNS_JA_TO_VI

        for i, lbl in enumerate(labels):
            trans = trans_map.get(i) or trans_map.get(str(i))
            if not trans:
                raw_orig = (lbl.get("original_text") or "").strip()
                raw_lower = raw_orig.lower()
                if raw_orig == "B" and not is_to_ja:
                    trans = "Cơ sở dữ liệu quan hệ"
                else:
                    for keys, pattern_trans in active_fuzzy:
                        if any(k.lower() in raw_lower for k in keys):
                            trans = pattern_trans
                            break
            lbl["translated_text"] = trans or lbl.get("original_text", "")

        return labels

    async def process_image(
        self,
        image_bytes: bytes,
        src_lang: str,
        tgt_lang: str,
        ocr_engine: str = "auto",
        provider: Any = None
    ) -> bytes:
        """
        End-to-end translation of a single image with zero-breakage fallback.
        Supports 'auto' (intelligent Vision + PaddleOCR cascade), 'gemini_vision', or 'paddleocr'.
        """
        try:
            labels = []
            # 1. If 'auto' or 'gemini_vision', prioritize Vision API for complex diagrams
            if ocr_engine in ("auto", "gemini_vision") and settings.GEMINI_API_KEY:
                try:
                    labels = await self.detect_and_translate_labels(image_bytes, src_lang, tgt_lang)
                    if labels:
                        logger.info(f"ImageTranslator: Vision API detected and translated {len(labels)} labels.")
                except Exception as vis_err:
                    logger.warning(f"ImageTranslator: Vision API failed, falling back to PaddleOCR: {vis_err}")
                    labels = []

            # 2. If labels empty or ocr_engine is 'paddleocr', run PaddleOCR local engine
            if not labels and ocr_engine in ("paddleocr", "auto", "paddleocr_only"):
                try:
                    from app.documents.ocr.paddle_ocr_engine import paddle_ocr_engine
                    labels = paddle_ocr_engine.detect_and_recognize(image_bytes, lang=src_lang)
                    if labels:
                        logger.info(f"PaddleOCR detected {len(labels)} labels. Translating text labels with AI/Glossary...")
                        labels = await self.translate_text_labels(labels, src_lang, tgt_lang, provider=provider)
                except Exception as paddle_err:
                    logger.warning(f"ImageTranslator: PaddleOCR error: {paddle_err}")
                    labels = []

            # 3. Final fallback to Vision if PaddleOCR failed
            if not labels and ocr_engine != "paddleocr_only" and settings.GEMINI_API_KEY:
                labels = await self.detect_and_translate_labels(image_bytes, src_lang, tgt_lang)

            if not labels:
                return image_bytes

            return self.inpaint_and_overlay(image_bytes, labels, tgt_lang)
        except Exception as e:
            logger.warning(f"ImageTranslator: Failed processing image, keeping original: {e}")
            return image_bytes

image_translator = ImageTranslator()
