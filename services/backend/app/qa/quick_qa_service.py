import json
import re
from typing import Dict, List, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Project, GlossaryTerm
from app.intelligence.models import WorkItem
from app.qa.models import TestCase, TestStep, QAOpenQuestion
from app.qa.engines import load_project_context, _next_tc_number
from app.qa.llm import generate_qa_json

class QuickQAService:
    """Human-centric QA Studio service for raw-thought polishing, bug RCA, Q&A 5W1H, ambiguity hunting, and mock test data."""

    @classmethod
    async def analyze(
        cls,
        payload: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        project_id = payload.get("project_id", "")
        spec_text = payload.get("spec_text", "").strip()
        mode = payload.get("mode", "test_case_polish")
        custom_instruction = payload.get("custom_instruction", "").strip()
        is_auto_harvest = payload.get("is_auto_harvest", False)
        target_language = payload.get("target_language", "bilingual")
        preferred_provider = payload.get("preferred_provider", "auto")
        model = payload.get("model")

        # Project and glossary context if auto-harvest is ON
        rag_context = ""
        decisions_context = ""
        if is_auto_harvest and project_id:
            try:
                decisions, siblings, r_ctx = await load_project_context(db, project_id)
                rag_context = r_ctx
                decisions_context = "\n".join([f"- {d.title}: {d.description[:150]}" for d in decisions[:8]])
            except Exception as e:
                logger.warning(f"Auto-harvest context lookup warning: {e}")

        if mode == "test_case_polish":
            return await cls._handle_test_case_polish(
                spec_text=spec_text,
                custom_instruction=custom_instruction,
                rag_context=rag_context,
                decisions_context=decisions_context,
                target_language=target_language,
                preferred_provider=preferred_provider,
                model=model
            )
        elif mode == "bug_draft":
            return await cls._handle_bug_draft(
                spec_text=spec_text,
                custom_instruction=custom_instruction,
                rag_context=rag_context,
                preferred_provider=preferred_provider,
                model=model
            )
        elif mode == "dev_inquiry":
            return await cls._handle_dev_inquiry(
                spec_text=spec_text,
                custom_instruction=custom_instruction,
                rag_context=rag_context,
                decisions_context=decisions_context,
                preferred_provider=preferred_provider,
                model=model
            )
        elif mode == "spec_ambiguity":
            return await cls._handle_spec_ambiguity(
                spec_text=spec_text,
                custom_instruction=custom_instruction,
                preferred_provider=preferred_provider,
                model=model
            )
        elif mode == "japan_test_data":
            return await cls._handle_japan_test_data(
                spec_text=spec_text,
                custom_instruction=custom_instruction,
                preferred_provider=preferred_provider,
                model=model
            )
        else: # quick_checklist
            return await cls._handle_quick_checklist(
                spec_text=spec_text,
                custom_instruction=custom_instruction,
                preferred_provider=preferred_provider,
                model=model
            )

    # =========================================================================
    # 1. TEST CASE POLISHER & EDGE-CASE EXPANDER
    # =========================================================================
    @classmethod
    async def _handle_test_case_polish(
        cls,
        spec_text: str,
        custom_instruction: str,
        rag_context: str,
        decisions_context: str,
        target_language: str,
        preferred_provider: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        system_instruction = (
            "You are a top-tier Japanese Software QA Architect and BrSE. "
            "The user will provide a casual, rough, or conversational test case idea (in Vietnamese or Japanese). "
            "Your job is to read and understand the core human intent, polish it into a flawless, enterprise-grade test case, "
            "and suggest 2-3 overlooked edge cases or boundary conditions."
        )

        prompt = f"""Human Test Idea / Casual Phrasing:
"{spec_text}"

Custom User Instruction (Guidance):
"{custom_instruction or 'None (make it clear, practical, and highly professional)'}"

Additional Project Knowledge (if available):
{decisions_context or '(none)'}
{rag_context or '(none)'}

Transform this raw idea into a structured Japanese-Vietnamese Test Case.
Return strict JSON matching:
{{
  "title_ja": "短いテストケース名（日本語）",
  "title_vi": "Tiêu đề test case súc tích (Tiếng Việt)",
  "case_type": "正常系 (Happy) | 異常系 (Negative) | 境界値 (Boundary) | 同時実行 (Concurrency) | 権限 (Permission)",
  "purpose_ja": "テスト目的（何を検証するか明確に）",
  "purpose_vi": "Mục đích kiểm thử rõ ràng",
  "preconditions_ja": ["前提条件 1...", "前提条件 2..."],
  "preconditions_vi": ["Tiền điều kiện 1...", "Tiền điều kiện 2..."],
  "steps": [
    {{
      "step_order": 1,
      "action_ja": "手順（具体的にクリックや入力対象を記述）",
      "action_vi": "Thao tác từng bước",
      "expected_ja": "期待結果（画面とDB/処理の挙動）",
      "expected_vi": "Kết quả kỳ vọng"
    }}
  ],
  "edge_case_tips": [
    "💡 Gợi ý trường hợp biên 1 (ví dụ: mạng chậm hoặc nhấn nút Back)",
    "💡 Gợi ý trường hợp biên 2"
  ],
  "formatted_markdown": "Full Markdown representation ready to copy into Excel or Slack"
}}"""

        parsed = await generate_qa_json(prompt, system_instruction, preferred_provider, model, max_tokens=2200)
        if not isinstance(parsed, dict) or "title_ja" not in parsed:
            # Fallback
            return {
                "title_ja": f"【検証】{spec_text[:40]}",
                "title_vi": f"Kiểm thử: {spec_text[:40]}",
                "case_type": "正常系 / 異常系",
                "purpose_ja": f"{spec_text}の挙動および整合性の確認",
                "purpose_vi": f"Kiểm tra tính đúng đắn khi thực hiện: {spec_text}",
                "preconditions_ja": ["対象画面にアクセスし、前提データが準備されていること。"],
                "preconditions_vi": ["Người dùng ở màn hình thao tác và có dữ liệu hợp lệ."],
                "steps": [
                    {
                        "step_order": 1,
                        "action_ja": f"{spec_text}を実行する。",
                        "action_vi": f"Thực hiện thao tác: {spec_text}",
                        "expected_ja": "システムが正常に応答し、エラーや二重処理が発生しないこと。",
                        "expected_vi": "Hệ thống phản hồi bình thường, không sinh lỗi hoặc xử lý trùng."
                    }
                ],
                "edge_case_tips": [
                    "💡 Thử nghiệm khi mạng bị delay (Slow 3G) hoặc timeout.",
                    "💡 Thử bấm phím Back/F5 của trình duyệt ngay sau khi thực hiện thao tác."
                ],
                "formatted_markdown": f"### 【テストケース】\n- **目的:** {spec_text}\n- **手順:** {spec_text}を実行\n- **期待値:** 正常に処理され不整合が起きないこと"
            }
        return parsed

    # =========================================================================
    # 2. BUG SYNTHESIZER & JAPANESE RCA DRAFTER
    # =========================================================================
    @classmethod
    async def _handle_bug_draft(
        cls,
        spec_text: str,
        custom_instruction: str,
        rag_context: str,
        preferred_provider: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        system_instruction = (
            "You are a Senior BrSE handling an urgent software defect for a Japanese client. "
            "Synthesize the raw bug report or error log into: 1) An immediate reassuring Japanese reply to the client, "
            "and 2) A structured defect report with phenomenon, reproduction, preliminary cause, and permanent fix."
        )

        prompt = f"""Raw Bug Description / Error Chat / Log:
"{spec_text}"

Custom Instruction:
"{custom_instruction or 'Format professionally for client report'}"

Return strict JSON:
{{
  "client_reply_keigo": "お客様への第一報返信（お礼、受付完了、調査中、本日○時までに進捗報告の旨を丁寧なビジネス敬語で）",
  "bug_title_ja": "不具合件名（日本語）",
  "bug_title_vi": "Tiêu đề lỗi (Tiếng Việt)",
  "severity": "CRITICAL | HIGH | MEDIUM | LOW",
  "environment": "本番環境 (Production) / ステージング (Staging)",
  "steps_to_reproduce": ["1. ...", "2. ..."],
  "actual_behavior": "発生事象（実測値）",
  "expected_behavior": "期待結果（期待値）",
  "preliminary_cause": "一次原因（ログや挙動からの推定原因）",
  "suggested_fix": {{
    "workaround": "暫定対応（ユーザー影響を抑える一時策）",
    "permanent": "恒久対応（根本的コード修正やリファクタリング）"
  }},
  "formatted_markdown": "Full Markdown defect report"
}}"""

        parsed = await generate_qa_json(prompt, system_instruction, preferred_provider, model, max_tokens=2200)
        if not isinstance(parsed, dict) or "bug_title_ja" not in parsed:
            return {
                "client_reply_keigo": "ご連絡いただきありがとうございます。事象を確認いたしました。現在、開発チームにてログおよび原因調査を最優先で進めております。追って進捗をご報告いたします。",
                "bug_title_ja": "【不具合報告】システム処理時の異常発生",
                "bug_title_vi": "Báo cáo lỗi phát sinh trong quá trình xử lý",
                "severity": "HIGH",
                "environment": "本番環境 (Production)",
                "steps_to_reproduce": ["1. 対象機能を開く", "2. 処理を実行する", "3. エラーが発生する"],
                "actual_behavior": spec_text[:200],
                "expected_behavior": "エラーが発生せず正常に完了すること",
                "preliminary_cause": "ログおよび例外処理の検証中",
                "suggested_fix": {
                    "workaround": "対象データの再実行またはサービス再起動",
                    "permanent": "例外ハンドリングの追加および入力値バリデーション強化"
                },
                "formatted_markdown": f"## 【不具合報告】\n- **事象:** {spec_text}\n- **対応:** 原因調査中"
            }
        return parsed

    # =========================================================================
    # 3. DEV QUERY ➔ 5W1H CLIENT INQUIRY FORMULATOR
    # =========================================================================
    @classmethod
    async def _handle_dev_inquiry(
        cls,
        spec_text: str,
        custom_instruction: str,
        rag_context: str,
        decisions_context: str,
        preferred_provider: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        system_instruction = (
            "You are an experienced IT BrSE communicating with Japanese clients. "
            "A Vietnamese dev asks a casual or incomplete technical question about specifications. "
            "Transform it into a formal Japanese Inquiry Sheet entry with 5W1H, offering Proposal A (recommended) vs Proposal B with Pros/Cons."
        )

        prompt = f"""Dev's Question / Doubt:
"{spec_text}"

Custom Instruction:
"{custom_instruction or 'Provide 2 logical proposals (A and B)'}"

Return strict JSON:
{{
  "inquiry_title_ja": "確認事項タイトル（簡潔に）",
  "inquiry_title_vi": "Tiêu đề câu hỏi xác nhận",
  "target_function": "対象画面・機能・API",
  "current_situation": "【現状】仕様書の現状の記述や開発側の把握内容",
  "issue_point": "【疑義・課題点】なぜ仕様の明確化が必要か",
  "proposal_a": {{
    "title": "A案（推奨）",
    "description": "A案の具体策",
    "pros": "メリット",
    "cons": "デメリット"
  }},
  "proposal_b": {{
    "title": "B案（代替案）",
    "description": "B案の具体策",
    "pros": "メリット",
    "cons": "デメリット"
  }},
  "confirmation_question": "【ご確認事項】（A案・B案のいずれで進めるか等、丁寧な敬語で結ぶ）",
  "formatted_markdown": "Full Markdown 5W1H inquiry entry"
}}"""

        parsed = await generate_qa_json(prompt, system_instruction, preferred_provider, model, max_tokens=2200)
        return parsed

    # =========================================================================
    # 4. SILENT ASSUMPTIONS & SPEC AMBIGUITY HUNTER
    # =========================================================================
    @classmethod
    async def _handle_spec_ambiguity(
        cls,
        spec_text: str,
        custom_instruction: str,
        preferred_provider: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        system_instruction = (
            "You are a vigilant BrSE and QA reviewer. Scan the Japanese specification text for dangerous ambiguous keywords "
            "such as 適宜, よしなに, 等, 速やかに, 検討中, 柔軟に, 一般的な, 原則として. "
            "Explain the technical risk for offshore dev and draft precise clarification questions."
        )

        prompt = f"""Specification Text:
"{spec_text}"

Custom Instruction:
"{custom_instruction or 'Check all ambiguous phrases'}"

Return strict JSON:
{{
  "ambiguity_score": "HIGH | MEDIUM | LOW",
  "found_issues": [
    {{
      "keyword": "検知された曖昧な単語（例: 適宜, 等）",
      "context_quote": "該当する文章の抜粋",
      "risk_description": "開発チームやテストでどのような誤解・手戻りが発生するリスクがあるか",
      "clarification_question": "お客様に確認すべき具体的な質問文（敬語）"
    }}
  ],
  "recommendations": "BrSEへのアドバイス・今後のアクション",
  "formatted_markdown": "Full Markdown analysis"
}}"""

        parsed = await generate_qa_json(prompt, system_instruction, preferred_provider, model, max_tokens=2000)
        return parsed

    # =========================================================================
    # 5. JAPAN TEST DATA & BOUNDARY GENERATOR
    # =========================================================================
    @classmethod
    async def _handle_japan_test_data(
        cls,
        spec_text: str,
        custom_instruction: str,
        preferred_provider: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        system_instruction = (
            "You are a Japanese QA Specialist. Generate realistic, authentic Japanese test data "
            "covering both valid standard formats and tricky boundary/edge conditions."
        )

        prompt = f"""Form / Test Context:
"{spec_text or 'General Japanese registration / profile / order form'}"

Custom Instruction:
"{custom_instruction or 'Generate valid sets and edge cases (Zenkaku/Hankaku)'}"

Return strict JSON:
{{
  "valid_test_data": [
    {{
      "label": "標準的な日本人氏名（東京）",
      "name_kanji": "山田 太郎",
      "name_kana": "ヤマダ タロウ",
      "name_romaji": "Yamada Taro",
      "postal_code": "100-0001",
      "address": "東京都千代田区千代田1-1 ○○ビル 3F",
      "phone_mobile": "090-1234-5678",
      "phone_fixed": "03-1234-5678",
      "email": "taro.yamada@example.co.jp"
    }},
    {{
      "label": "女性氏名・地方都市（大阪）",
      "name_kanji": "佐藤 花子",
      "name_kana": "サトウ ハナコ",
      "name_romaji": "Sato Hanako",
      "postal_code": "530-0001",
      "address": "大阪府大阪市北区梅田1-1-3 大阪駅前第3ビル 15F",
      "phone_mobile": "080-9876-5432",
      "phone_fixed": "06-6123-4567",
      "email": "hanako.sato@example.co.jp"
    }}
  ],
  "boundary_edge_cases": [
    {{
      "category": "半角カナ (Hankaku Katakana)",
      "sample": "ﾔﾏﾀﾞ ﾀﾛｳ",
      "purpose": "半角文字の自動全角変換またはバリデーションエラーの検証"
    }},
    {{
      "category": "旧字体・異体字 (Kanji Variants)",
      "sample": "髙橋 﨑山 (髙, 﨑)",
      "purpose": "外字・文字化け（UTF-8 / Shift-JIS）の耐性検証"
    }},
    {{
      "category": "環境依存文字・絵文字",
      "sample": "㈱ ㈲ № ① 😊",
      "purpose": "データベース保存時のエンコーディングエラー検証"
    }},
    {{
      "category": "最大文字数・空白トリム",
      "sample": "　山田　太郎　 (前後全角スペース付き)",
      "purpose": "自動トリム処理および最大長超過の検証"
    }}
  ],
  "formatted_markdown": "Full Markdown formatted test data table ready to copy into spreadsheet"
}}"""

        parsed = await generate_qa_json(prompt, system_instruction, preferred_provider, model, max_tokens=2200)
        return parsed

    # =========================================================================
    # 6. QUICK CHECKLIST GENERATOR
    # =========================================================================
    @classmethod
    async def _handle_quick_checklist(
        cls,
        spec_text: str,
        custom_instruction: str,
        preferred_provider: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        system_instruction = (
            "You are a Pragmatic QA Lead. Produce 5-8 concise, high-value, single-step checklist items "
            "for fast pre-delivery validation. Keep it lightweight, bilingual, and actionable."
        )

        prompt = f"""Feature / Change Description:
"{spec_text}"

Custom Instruction:
"{custom_instruction or 'Keep it short and concise'}"

Return strict JSON:
{{
  "checklist_title": "チェックリストタイトル",
  "items": [
    {{
      "no": 1,
      "check_point_ja": "確認項目（日本語）",
      "check_point_vi": "Điểm cần kiểm tra (Tiếng Việt)",
      "importance": "MUST | SHOULD",
      "expected_result": "期待される挙動"
    }}
  ],
  "formatted_markdown": "Full Markdown checklist table"
}}"""

        parsed = await generate_qa_json(prompt, system_instruction, preferred_provider, model, max_tokens=1800)
        return parsed
