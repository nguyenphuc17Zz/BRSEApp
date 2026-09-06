import urllib.request
import urllib.parse
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"
DAITOH_PID = "10751429-c6ce-40a3-a700-45df4946909f"

def req(url, method="GET", data=None):
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))

def test_stakeholder_flow():
    print("--- 1. Testing GET stakeholders (Expect 0 mock data) ---")
    status, items = req(f"{BASE_URL}/api/intelligence/stakeholders?project_id={DAITOH_PID}")
    assert status == 200
    for it in items:
        if it['name'].startswith("Kato-san"):
            req(f"{BASE_URL}/api/intelligence/stakeholders/{it['id']}", method="DELETE")
    
    status, items = req(f"{BASE_URL}/api/intelligence/stakeholders?project_id={DAITOH_PID}")
    print(f"Current count: {len(items)}")
    for it in items:
        print(f" - {it['name']} ({it['role']})")
    assert not any(m in [i['name'] for i in items] for m in ["Suzuki-san", "Tanaka-san", "Yamada-san"]), "Mock data still present!"

    print("\n--- 2. Testing CREATE stakeholder ---")
    create_payload = {
        "project_id": DAITOH_PID,
        "name": "Kato-san (Customer PM)",
        "role": "Client PM",
        "organization": "Khách hàng Nhật",
        "platform": "slack",
        "notes": "Người quyết định các spec của màn hình gia công ngoài"
    }
    status, created = req(f"{BASE_URL}/api/intelligence/stakeholders", method="POST", data=create_payload)
    assert status == 200
    st_id = created["id"]
    print(f"Created stakeholder ID: {st_id}, Name: {created['name']}")

    print("\n--- 3. Testing UPDATE stakeholder ---")
    update_payload = {
        "role": "Product Owner",
        "notes": "Đã cập nhật vai trò PO phụ trách release 1.0"
    }
    status, updated = req(f"{BASE_URL}/api/intelligence/stakeholders/{st_id}", method="PUT", data=update_payload)
    assert status == 200
    print(f"Updated role: {updated['role']}, Notes: {updated['notes']}")
    assert updated["role"] == "Product Owner"

    print("\n--- 4. Testing CLEAN-MOCK endpoint ---")
    status, clean_res = req(f"{BASE_URL}/api/intelligence/stakeholders/clean-mock?project_id={DAITOH_PID}", method="POST")
    assert status == 200
    print(f"Clean mock response: {clean_res}")

    print("\n--- 5. Testing DELETE stakeholder ---")
    status, del_res = req(f"{BASE_URL}/api/intelligence/stakeholders/{st_id}", method="DELETE")
    assert status == 200
    print(f"Delete response: {del_res}")

    status, final_items = req(f"{BASE_URL}/api/intelligence/stakeholders?project_id={DAITOH_PID}")
    matched = [i for i in final_items if i["id"] == st_id]
    assert len(matched) == 0, "Stakeholder was not deleted!"
    print("Stakeholder successfully verified deleted.")

    print("\n=== ALL STAKEHOLDER CRUD & CLEAN TESTS PASSED! ===")

if __name__ == "__main__":
    test_stakeholder_flow()
