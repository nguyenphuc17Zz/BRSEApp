import urllib.request
import urllib.parse
import json
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"
DAITOH_PID = "10751429-c6ce-40a3-a700-45df4946909f"

def req(url, method="GET", data=None):
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))

def test_line_workspace():
    print("=== 1. KIỂM TRA GET LINE MESSAGES THEO PROJECT ===")
    status, res = req(f"{BASE_URL}/api/line/messages?project_id={DAITOH_PID}")
    assert status == 200
    print(f"Số tin nhắn LINE hiện tại của dự án Daitoh: {len(res['messages'])}")

    print("\n=== 2. MÔ PHỎNG TIN NHẮN LINE HỎI ĐẶC TẢ CSV (KÍCH HOẠT RAG SPEC GROUNDING) ===")
    sim_payload = {
        "text": "CSVインポート時のキー項目と、画面上で修正可能な項目について仕様を教えてください。",
        "sender": "Kato-san (Customer PM)",
        "project_id": DAITOH_PID,
        "provider": "groq",
        "model": "qwen/qwen3.8-27b"
    }
    status, msg = req(f"{BASE_URL}/api/line/simulate", method="POST", data=sim_payload)
    assert status == 200
    msg_id = msg["id"]
    print(f"Tin nhắn đã được lưu vào CSDL với ID: {msg_id}")
    print(f"Detected Intent: {msg.get('detected_intent')}")
    print(f"RAG Spec Sources Grounding count: {len(msg.get('rag_sources', []))}")
    for src in msg.get('rag_sources', []):
        print(f"  📄 Tham chiếu Spec: {src.get('file_name')} #{src.get('chunk_index')}")
    
    print("\nCác phương án trả lời AI đề xuất:")
    for r in msg.get("suggested_replies", []):
        print(f"  [{r.get('style')}]: {r.get('text')}")

    print("\nSync sang BrSE Work Inbox:")
    sync = msg.get("sync_result", {})
    print(f"  Yêu cầu: {sync.get('requirements', 0)}, Lỗi: {sync.get('bugs', 0)}, Deadlines: {sync.get('deadlines', 0)}")

    print("\n=== 3. KIỂM TRA TÁI TẠO CÂU TRẢ LỜI (REGENERATE REPLY) ===")
    status, regen = req(f"{BASE_URL}/api/line/messages/{msg_id}/regenerate", method="POST", data={"provider": "groq"})
    assert status == 200
    print(f"Tái tạo thành công: {len(regen.get('suggested_replies', []))} phương án mới.")

    print("\n=== 4. KIỂM TRA XÓA TIN NHẮN ĐƠN LẺ KHỎI CSDL ===")
    status, del_res = req(f"{BASE_URL}/api/line/messages/{msg_id}", method="DELETE")
    assert status == 200
    print(f"Kết quả xóa: {del_res}")

    status, check_del = req(f"{BASE_URL}/api/line/messages?project_id={DAITOH_PID}")
    assert not any(m["id"] == msg_id for m in check_del["messages"]), "Tin nhắn chưa bị xóa!"
    print("Xác nhận: Tin nhắn đã biến mất hoàn toàn khỏi CSDL.")

    print("\n=== 5. KIỂM TRA ZERO-WASTE CASCADING DELETION CỦA TIN NHẮN LINE THEO PROJECT ===")
    # Tạo project tạm
    p_code = f"LINE_CASC_{int(time.time())}"
    status, tmp_proj = req(f"{BASE_URL}/api/projects", method="POST", data={"name": "Dự án Tạm Test LINE Cascade", "code": p_code})
    tmp_pid = tmp_proj["id"]
    print(f"Tạo dự án tạm ID: {tmp_pid}")

    # Tạo tin nhắn LINE thuộc project tạm
    status, tmp_line = req(f"{BASE_URL}/api/line/simulate", method="POST", data={
        "text": "Tin nhắn test cascade deletion",
        "sender": "Test User",
        "project_id": tmp_pid
    })
    tmp_line_id = tmp_line["id"]
    print(f"Tạo tin nhắn LINE ID: {tmp_line_id}")

    # Xóa project tạm
    status, del_p = req(f"{BASE_URL}/api/projects/{tmp_pid}", method="DELETE")
    assert status == 200
    print("Đã gọi xóa project tạm.")

    # Kiểm tra tin nhắn LINE có bị xóa dây chuyền không
    status, check_tmp = req(f"{BASE_URL}/api/line/messages?project_id={tmp_pid}")
    assert len(check_tmp["messages"]) == 0, "Tin nhắn LINE không bị xóa dây chuyền!"
    print("Xác nhận: Tin nhắn LINE ĐÃ BỊ XÓA DÂY CHUYỀN THEO PROJECT (0 rác tài nguyên)!")

    print("\n🎉 TẤT CẢ CÁC BÀI KIỂM THỬ LINE SMART WORKSPACE ĐÃ ĐẠT CHUẨN 100%!")

if __name__ == "__main__":
    test_line_workspace()
