import pytest
from app.core.security import encrypt_credential, decrypt_credential, mask_api_key, scan_sensitive_data, mask_sensitive_data
from app.engine.router import TaskAnalyzer, RoutingEngine
from app.engine.qa import QAChecker
from app.engine.pipeline import detect_language

def test_credential_encryption_and_masking():
    plain = "gsk_secret_key_1234567890abcdef"
    cipher = encrypt_credential(plain)
    assert cipher != plain
    decrypted = decrypt_credential(cipher)
    assert decrypted == plain

    masked = mask_api_key(plain)
    assert masked == "gsk_...cdef"
    assert mask_api_key(None) == ""

def test_sensitive_data_detection():
    text = "Please send credentials to dev@example.com or call +84987654321 with token: api_key='sk_test_1234567890123456'."
    findings = scan_sensitive_data(text)
    types = [f["type"] for f in findings]
    assert "email" in types
    
    sanitized, _ = mask_sensitive_data(text)
    assert "dev@example.com" not in sanitized
    assert "[EMAIL_REDACTED]" in sanitized

def test_language_detection():
    assert detect_language("この件は対象外です。") == "ja"
    assert detect_language("認証機能の実装について") == "ja"
    assert detect_language("Hệ thống ngân hàng trực tuyến") == "vi"
    assert detect_language("Xin chào tôi là comtor") == "vi"
    assert detect_language("Tài liệu đặc tả chức năng đăng nhập") == "vi"
    assert detect_language("System Authentication and Authorization Specification") == "en"
    assert detect_language("API endpoint documentation for login and refresh") == "en"
    assert detect_language("") == "ja"

def test_task_analyzer_and_ambiguity():
    # Ambiguous IT Japanese
    analysis = TaskAnalyzer.analyze("この件は対象外です。")
    assert analysis["is_ambiguous"] is True
    assert analysis["task_type"] == "ambiguous_translation"

    # Technical Japanese
    analysis_tech = TaskAnalyzer.analyze("OAuth認証機能とAPI Gatewayの例外処理について本番環境へデプロイする。")
    assert "認証" in analysis_tech["it_keywords"]
    assert analysis_tech["task_type"] == "technical_translation"

def test_router_engine_selection():
    router = RoutingEngine()
    analysis_ambiguous = {"task_type": "ambiguous_translation", "has_sensitive": False}
    primary, fallbacks, model = router.select_route(analysis_ambiguous)
    assert primary == "gemini"
    assert "groq" in fallbacks
    assert "ollama" in fallbacks

    # Sensitive data route to Ollama
    analysis_sensitive = {"task_type": "business_translation", "has_sensitive": True}
    primary_sens, _, _ = router.select_route(analysis_sensitive)
    assert primary_sens == "ollama"

def test_qa_checker():
    # Number mismatch
    source = "Timeout is 30 seconds."
    target_wrong = "Thời gian chờ là 60 giây."
    warnings = QAChecker.run_qa(source, target_wrong)
    assert any("Number inconsistency" in w for w in warnings)

    # Glossary compliance check
    source_term = "本番環境で障害が発生しました。"
    target_good = "Đã xảy ra sự cố tại môi trường thực tế."
    glossary = [{"source_term": "障害", "target_term": "sự cố"}]
    warnings_good = QAChecker.run_qa(source_term, target_good, glossary)
    assert not any("Glossary term warning" in w for w in warnings_good)

    target_missing_glossary = "Đã xảy ra lỗi tại môi trường thực tế."
    warnings_bad = QAChecker.run_qa(source_term, target_missing_glossary, glossary)
    assert any("Glossary term warning" in w for w in warnings_bad)
