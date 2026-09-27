import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

from app.core.logging import logger

class SlideReportService:
    """Manages PowerPoint (.pptx) template analysis, auto-filling, and default presentation generation."""

    @classmethod
    def analyze_slide_template(cls, pptx_path: str) -> Dict[str, Any]:
        """Inspects a user-uploaded PPTX presentation and extracts slide count and text placeholders."""
        if not os.path.exists(pptx_path):
            raise FileNotFoundError(f"Template slide not found at {pptx_path}")

        prs = Presentation(pptx_path)
        slides_info = []

        for idx, slide in enumerate(prs.slides):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    t = shape.text_frame.text.strip()
                    if t:
                        texts.append(t[:100])
            slides_info.append({
                "slide_index": idx + 1,
                "shape_count": len(slide.shapes),
                "snippets": texts[:5]
            })

        return {
            "slide_count": len(prs.slides),
            "slides": slides_info,
            "filename": Path(pptx_path).name
        }

    @classmethod
    def fill_slide_template(
        cls,
        template_path: str,
        report_data: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        Clones an existing presentation template (.pptx) and replaces old placeholders,
        card boxes, and table rows with fresh report data, preserving 100% of company
        branding, logos, layout, shapes, and typography.
        """
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")

        prs = Presentation(template_path)

        project_name = report_data.get("project_name", "IT Project")
        report_title = report_data.get("title", "進捗報告書")
        report_date = report_data.get("report_date", "")
        sender_name = report_data.get("sender_name", "BrSE / Offshore Team")
        recipient_name = report_data.get("recipient_name", "お客様 (Client)")
        target_language = report_data.get("target_language", "ja")
        is_vi = target_language == "vi"
        
        achievements = report_data.get("achievements", [])
        plans = report_data.get("plans", [])
        issues = report_data.get("issues", [])
        summary_text = report_data.get("summary_text", "")

        achievements_str = "\n".join([f"• {a}" for a in achievements]) if achievements else ("• Đã hoàn thành các hạng mục theo kế hoạch." if is_vi else "• 計画通り順調に進捗しております。")
        plans_str = "\n".join([f"• {p}" for p in plans]) if plans else ("• Tiếp tục triển khai các mục tiêu tiếp theo." if is_vi else "• 予定通りのマイルストーンを推進いたします。")
        issues_str = "\n".join([f"• {i}" for i in issues]) if issues else ("• Hiện tại không có blocker nghiêm trọng." if is_vi else "• 現在、ブロッカーとなる重大な課題はございません。")

        # Multi-lingual placeholder map (VI, JA, EN)
        replacements = {
            "{{title}}": report_title,
            "{{tiêu_đề}}": report_title,
            "{{tiêu đề}}": report_title,
            "{{project_name}}": project_name,
            "{{dự_án}}": project_name,
            "{{dự án}}": project_name,
            "{{date}}": report_date,
            "{{ngày}}": report_date,
            "{{ngày báo cáo}}": report_date,
            "{{sender}}": sender_name,
            "{{người_gửi}}": sender_name,
            "{{người báo cáo}}": sender_name,
            "{{recipient}}": recipient_name,
            "{{người_nhận}}": recipient_name,
            "{{khách hàng}}": recipient_name,
            "{{achievements}}": achievements_str,
            "{{hoàn_thành}}": achievements_str,
            "{{thành tựu}}": achievements_str,
            "{{plans}}": plans_str,
            "{{kế_hoạch}}": plans_str,
            "{{issues}}": issues_str,
            "{{vấn_đề}}": issues_str,
            "{{vướng mắc}}": issues_str,
            "{{summary}}": summary_text,
            "{{tóm_tắt}}": summary_text,
            "【タイトル】": report_title,
            "【日付】": report_date,
            "【実績】": achievements_str,
            "【予定】": plans_str,
            "【課題】": issues_str,
            "【概要】": summary_text
        }

        # Step 1: Explicit keyword replacement in text frames
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        orig_text = paragraph.text
                        for k, v in replacements.items():
                            if k in orig_text:
                                paragraph.text = orig_text.replace(k, v)
                                orig_text = paragraph.text

        # Step 2: Semantic matching for card boxes beneath headers (VI, JA, EN)
        ach_keywords = ["実績", "完了", "対応実績", "hoàn thành", "thực hiện", "kết quả", "đã xong", "achievement", "completed", "done"]
        plan_keywords = ["予定", "計画", "来週", "kế hoạch", "dự kiến", "tiếp theo", "mục tiêu", "plan", "milestone", "next step", "upcoming"]
        issue_keywords = ["課題", "リスク", "確認事項", "催促", "ご相談", "vấn đề", "vướng mắc", "chờ duyệt", "cần xác nhận", "blocker", "risk", "issue", "inquiry"]

        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame and len(shape.text_frame.text) < 50:
                    header = shape.text_frame.text.strip().lower()
                    if any(k in header for k in ach_keywords) and achievements:
                        cls._append_bullets_to_nearby_shape(slide, shape, achievements)
                    elif any(k in header for k in plan_keywords) and plans:
                        cls._append_bullets_to_nearby_shape(slide, shape, plans)
                    elif any(k in header for k in issue_keywords) and issues:
                        cls._append_bullets_to_nearby_shape(slide, shape, issues)

        # Step 3: Support for PPTX Tables (Task grids / WBS progress tables)
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_table:
                    cls._populate_pptx_table(shape.table, achievements, plans, is_vi)

        dirname = os.path.dirname(output_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        prs.save(output_path)
        logger.info(f"Filled slide template saved successfully to {output_path}")
        return output_path

    @classmethod
    def _populate_pptx_table(cls, table, achievements: List[str], plans: List[str], is_vi: bool):
        """Intelligently fills task tables in presentation templates."""
        try:
            if len(table.rows) < 2 or len(table.columns) < 2:
                return

            # Check header row
            header_texts = [cell.text.strip().lower() for cell in table.rows[0].cells]
            task_col_idx = 1 if len(header_texts) > 1 else 0
            status_col_idx = None
            
            for idx, h in enumerate(header_texts):
                if any(k in h for k in ["hạng mục", "công việc", "task", "項目", "内容", "title"]):
                    task_col_idx = idx
                elif any(k in h for k in ["tiến độ", "trạng thái", "status", "進捗", "状況"]):
                    status_col_idx = idx

            # Fill rows
            all_items = [(a, "Hoàn thành" if is_vi else "完了") for a in achievements] + \
                        [(p, "Kế hoạch" if is_vi else "予定") for p in plans]
            
            row_idx = 1
            for task_desc, status_label in all_items:
                if row_idx >= len(table.rows):
                    break
                row = table.rows[row_idx]
                # Set task text
                if task_col_idx < len(row.cells):
                    row.cells[task_col_idx].text = task_desc
                # Set status
                if status_col_idx is not None and status_col_idx < len(row.cells):
                    row.cells[status_col_idx].text = status_label
                row_idx += 1
        except Exception as e:
            logger.debug(f"Table population skipped: {e}")

    @classmethod
    def _append_bullets_to_nearby_shape(cls, slide, header_shape, items: List[str]):
        """Finds the text container immediately beneath or beside a section header and injects bullet points, preserving original fonts and colors."""
        try:
            h_top = header_shape.top
            h_left = header_shape.left
            
            candidates = []
            for s in slide.shapes:
                if s != header_shape and s.has_text_frame:
                    if s.top >= h_top and abs(s.left - h_left) < Inches(3.5):
                        candidates.append(s)
            
            if candidates:
                target = min(candidates, key=lambda s: s.top)
                tf = target.text_frame
                
                # Extract original font style from existing runs if available
                orig_font_name = "Meiryo"
                orig_font_size = Pt(13)
                orig_font_color = None
                
                for p in tf.paragraphs:
                    for r in p.runs:
                        if r.font.name:
                            orig_font_name = r.font.name
                        if r.font.size:
                            orig_font_size = r.font.size
                        if r.font.color and r.font.color.type is not None:
                            try:
                                orig_font_color = r.font.color.rgb
                            except Exception:
                                pass
                        break
                    if orig_font_name != "Meiryo":
                        break

                tf.clear()
                for it in items[:7]:
                    p = tf.add_paragraph()
                    r = p.add_run()
                    r.text = f"• {it}"
                    r.font.name = orig_font_name
                    r.font.size = orig_font_size
                    if orig_font_color:
                        r.font.color.rgb = orig_font_color
                    p.space_before = Pt(6)
        except Exception as e:
            logger.debug(f"Nearby shape bullet insertion skipped: {e}")

    @classmethod
    def generate_default_weekly_slide(
        cls,
        report_data: Dict[str, Any],
        output_path: str
    ) -> str:
        """Generates an executive, modern 16:9 Japanese weekly/daily report presentation from scratch."""
        prs = Presentation()
        # Set 16:9 widescreen dimensions (13.33 x 7.5 inches)
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        blank_slide_layout = prs.slide_layouts[6] # Blank slide

        # Color Palette
        navy_dark = RGBColor(15, 23, 42)       # Slate 900
        blue_accent = RGBColor(37, 99, 235)     # Blue 600
        text_primary = RGBColor(30, 41, 59)     # Slate 800
        text_muted = RGBColor(100, 116, 139)    # Slate 500
        card_bg = RGBColor(248, 250, 252)       # Slate 50
        card_border = RGBColor(226, 232, 240)   # Slate 200
        green_tag = RGBColor(22, 163, 74)       # Emerald 600
        amber_tag = RGBColor(217, 119, 6)       # Amber 600

        project_name = report_data.get("project_name", "IT Project")
        report_title = report_data.get("title", "週次進捗報告書 (Weekly Report)")
        report_date = report_data.get("report_date", "")
        sender_name = report_data.get("sender_name", "Offshore BrSE / Development Team")
        recipient_name = report_data.get("recipient_name", "お客様 (Client Project Team)")

        target_language = report_data.get("target_language", "ja")
        is_vi = target_language == "vi"

        achievements = report_data.get("achievements", [])
        plans = report_data.get("plans", [])
        issues = report_data.get("issues", [])
        summary_text = report_data.get("summary_text", "Báo cáo tiến độ dự án" if is_vi else "今週のマイルストーン及び作業進捗状況をご報告いたします。")

        # =========================================================================
        # SLIDE 1: Title Slide
        # =========================================================================
        slide1 = prs.slides.add_slide(blank_slide_layout)
        
        # Background Accent Bar (Left side)
        accent_bar = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.4), Inches(7.5))
        accent_bar.fill.solid()
        accent_bar.fill.fore_color.rgb = blue_accent
        accent_bar.line.color.rgb = blue_accent

        # Title Box
        title_box = slide1.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.5), Inches(3.0))
        tf1 = title_box.text_frame
        tf1.word_wrap = True

        p_proj = tf1.paragraphs[0]
        p_proj.text = f"【{project_name}】"
        p_proj.font.size = Pt(20)
        p_proj.font.bold = True
        p_proj.font.color.rgb = blue_accent

        p_title = tf1.add_paragraph()
        p_title.text = report_title
        p_title.font.size = Pt(36)
        p_title.font.bold = True
        p_title.font.color.rgb = navy_dark
        p_title.space_before = Pt(10)

        p_date = tf1.add_paragraph()
        p_date.text = f"Ngày báo cáo: {report_date}  |  Kính gửi: {recipient_name}" if is_vi else f"報告日: {report_date}  |  宛先: {recipient_name}"
        p_date.font.size = Pt(14)
        p_date.font.color.rgb = text_muted
        p_date.space_before = Pt(16)

        p_sender = tf1.add_paragraph()
        p_sender.text = f"Người báo cáo: {sender_name}" if is_vi else f"報告者: {sender_name}"
        p_sender.font.size = Pt(13)
        p_sender.font.color.rgb = text_muted

        # =========================================================================
        # SLIDE 2: Achievements & Completed Tasks (今週の実績)
        # =========================================================================
        slide2 = prs.slides.add_slide(blank_slide_layout)
        s2_header = "1. Kết quả thực hiện & Hạng mục đã hoàn thành" if is_vi else "1. 今週の対応実績・完了事項"
        cls._add_slide_header(slide2, project_name, s2_header, blue_accent, navy_dark)

        # Left Column: Summary Card
        card1 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.8), Inches(4.5), Inches(4.8))
        card1.fill.solid()
        card1.fill.fore_color.rgb = card_bg
        card1.line.color.rgb = card_border

        tf_c1 = card1.text_frame
        tf_c1.word_wrap = True
        p_h1 = tf_c1.paragraphs[0]
        p_h1.text = "📌 Tóm tắt tiến độ" if is_vi else "📌 進捗ハイライト・サマリー"
        p_h1.font.size = Pt(16)
        p_h1.font.bold = True
        p_h1.font.color.rgb = blue_accent

        p_b1 = tf_c1.add_paragraph()
        p_b1.text = summary_text
        p_b1.font.size = Pt(13)
        p_b1.font.color.rgb = text_primary
        p_b1.space_before = Pt(14)

        # Right Column: Achievements List
        card2 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.8), Inches(1.8), Inches(6.5), Inches(4.8))
        card2.fill.solid()
        card2.fill.fore_color.rgb = card_bg
        card2.line.color.rgb = card_border

        tf_c2 = card2.text_frame
        tf_c2.word_wrap = True
        p_h2 = tf_c2.paragraphs[0]
        p_h2.text = "✅ Danh sách công việc hoàn thành" if is_vi else "✅ 実装・対応完了タスク一覧"
        p_h2.font.size = Pt(16)
        p_h2.font.bold = True
        p_h2.font.color.rgb = green_tag

        items_to_show = achievements if achievements else (["Đã hoàn thành các tính năng chính và kiểm thử theo kế hoạch."] if is_vi else ["計画通り主要機能の実装および単体テストを順調に完了しました。"])
        for ach in items_to_show[:7]:
            p = tf_c2.add_paragraph()
            p.text = f"• {ach}"
            p.font.size = Pt(13)
            p.font.color.rgb = text_primary
            p.space_before = Pt(8)

        # =========================================================================
        # SLIDE 3: Next Plans & Upcoming Milestones (来週の作業計画)
        # =========================================================================
        slide3 = prs.slides.add_slide(blank_slide_layout)
        s3_header = "2. Kế hoạch công việc tiếp theo & Mục tiêu" if is_vi else "2. 来週の作業計画 & 直近マイルストーン"
        cls._add_slide_header(slide3, project_name, s3_header, blue_accent, navy_dark)

        # Full Width Container
        card3 = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.8), Inches(11.3), Inches(4.8))
        card3.fill.solid()
        card3.fill.fore_color.rgb = card_bg
        card3.line.color.rgb = card_border

        tf_c3 = card3.text_frame
        tf_c3.word_wrap = True
        p_h3 = tf_c3.paragraphs[0]
        p_h3.text = "📅 Kế hoạch triển khai & Lịch trình" if is_vi else "📅 推進予定タスク & スケジュール方針"
        p_h3.font.size = Pt(16)
        p_h3.font.bold = True
        p_h3.font.color.rgb = blue_accent

        plan_items = plans if plans else (["Tiếp tục triển khai test tích hợp và hoàn thiện spec."] if is_vi else ["結合テストの実施およびテストケース消化を推進いたします。"])
        for pl in plan_items[:8]:
            p = tf_c3.add_paragraph()
            p.text = f"• {pl}"
            p.font.size = Pt(13)
            p.font.color.rgb = text_primary
            p.space_before = Pt(10)

        # =========================================================================
        # SLIDE 4: Blockers, Risks & Saisoku (課題・お客様へのご確認事項)
        # =========================================================================
        slide4 = prs.slides.add_slide(blank_slide_layout)
        s4_header = "3. Vấn đề vướng mắc & Cần đối tác phản hồi" if is_vi else "3. 課題・リスク管理 & お客様へのご確認事項"
        cls._add_slide_header(slide4, project_name, s4_header, amber_tag, navy_dark)

        card4 = slide4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.8), Inches(11.3), Inches(4.8))
        card4.fill.solid()
        card4.fill.fore_color.rgb = card_bg
        card4.line.color.rgb = card_border

        tf_c4 = card4.text_frame
        tf_c4.word_wrap = True
        p_h4 = tf_c4.paragraphs[0]
        p_h4.text = "⚠️ Các hạng mục chờ xác nhận & Cần hỗ trợ" if is_vi else "⚠️ 現在の確認待ち事項・ご相談（催促・仕様確認）"
        p_h4.font.size = Pt(16)
        p_h4.font.bold = True
        p_h4.font.color.rgb = amber_tag

        issue_items = issues if issues else (["Hiện tại không có blocker nghiêm trọng nào ảnh hưởng tới tiến độ."] if is_vi else ["現在、進捗を阻害する重大なブロッカーは発生しておりません。"])
        for iss in issue_items[:7]:
            p = tf_c4.add_paragraph()
            p.text = f"• {iss}"
            p.font.size = Pt(13)
            p.font.color.rgb = text_primary
            p.space_before = Pt(10)

        dirname = os.path.dirname(output_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        prs.save(output_path)
        logger.info(f"Default Japanese executive presentation generated at {output_path}")
        return output_path

    @classmethod
    def _add_slide_header(cls, slide, project_name: str, section_title: str, accent_color: RGBColor, title_color: RGBColor):
        """Standardized header for interior presentation slides."""
        # Top Accent Line
        top_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(0.6), Inches(11.3), Inches(0.04))
        top_line.fill.solid()
        top_line.fill.fore_color.rgb = accent_color
        top_line.line.color.rgb = accent_color

        header_box = slide.shapes.add_textbox(Inches(1.0), Inches(0.75), Inches(11.3), Inches(0.8))
        tf = header_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = section_title
        p.font.size = Pt(22)
        p.font.bold = True
        p.font.color.rgb = title_color

        p_sub = tf.add_paragraph()
        p_sub.text = f"Project: {project_name}"
        p_sub.font.size = Pt(11)
        p_sub.font.color.rgb = RGBColor(148, 163, 184)
