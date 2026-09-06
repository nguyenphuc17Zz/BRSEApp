import httpx

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ID = "10751429-c6ce-40a3-a700-45df4946909f"

def test_work_items_lifecycle():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        print("[1] Fetching work inbox...")
        r = client.get("/api/brse-dashboard/inbox", params={"project_id": PROJECT_ID})
        assert r.status_code == 200, f"Inbox fetch failed: {r.text}"
        inbox = r.json()
        all_items = (
            inbox.get("requirements", []) +
            inbox.get("bugs", []) +
            inbox.get("decisions", []) +
            inbox.get("questions", []) +
            inbox.get("deadlines", [])
        )
        print(f"Total work items in inbox: {len(all_items)}")
        if not all_items:
            print("No work items to test. Creating a draft work item...")
            create_res = client.post("/api/work-items", json={
                "project_id": PROJECT_ID,
                "type": "REQUIREMENT",
                "title": "Test Lifecycle Item",
                "description": "Lifecycle item for test",
                "priority": "HIGH",
                "status": "PROPOSED"
            })
            assert create_res.status_code == 200, f"Create failed: {create_res.text}"
            target_item = create_res.json()
            item_id = target_item["id"]
            should_delete = True
        else:
            target_item = all_items[0]
            item_id = target_item["id"]
            original_status = target_item.get("status", "PROPOSED")
            should_delete = False
        
        print(f"[2] Testing with Item ID: {item_id}")
        
        # 1. Confirm
        print("Testing Confirm...")
        conf_res = client.post(f"/api/work-items/{item_id}/confirm")
        assert conf_res.status_code == 200, f"Confirm failed: {conf_res.text}"
        conf_data = conf_res.json()
        assert conf_data["status"] == "CONFIRMED", f"Expected CONFIRMED, got {conf_data['status']}"
        print("Confirm OK: status is CONFIRMED")
        
        # 2. Reject
        print("Testing Reject...")
        rej_res = client.post(f"/api/work-items/{item_id}/reject")
        assert rej_res.status_code == 200, f"Reject failed: {rej_res.text}"
        rej_data = rej_res.json()
        assert rej_data["status"] == "REJECTED", f"Expected REJECTED, got {rej_data['status']}"
        print("Reject OK: status is REJECTED")
        
        # 3. Reset
        print("Testing Reset...")
        rst_res = client.post(f"/api/work-items/{item_id}/reset")
        assert rst_res.status_code == 200, f"Reset failed: {rst_res.text}"
        rst_data = rst_res.json()
        assert rst_data["status"] == "PROPOSED", f"Expected PROPOSED, got {rst_data['status']}"
        print("Reset OK: status is PROPOSED")
        
        # Cleanup if temporary
        if should_delete:
            del_res = client.delete(f"/api/work-items/{item_id}")
            assert del_res.status_code == 200
            print("Cleaned up temporary test work item.")
        else:
            if original_status == "CONFIRMED":
                client.post(f"/api/work-items/{item_id}/confirm")
            elif original_status == "REJECTED":
                client.post(f"/api/work-items/{item_id}/reject")
            print(f"Restored work item back to original status: {original_status}")
        
        # 4. Stakeholders Check
        print("[3] Testing Stakeholders for LINE and BrSE...")
        stk_res = client.get("/api/intelligence/stakeholders", params={"project_id": PROJECT_ID})
        assert stk_res.status_code == 200, f"Stakeholders fetch failed: {stk_res.text}"
        stk_list = stk_res.json()
        print(f"Stakeholders count: {len(stk_list)}")
        for s in stk_list:
            print(f" - {s['name']} ({s['role']}, platform: {s.get('platform')})")
            
        print("\nALL LIFECYCLE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_work_items_lifecycle()
