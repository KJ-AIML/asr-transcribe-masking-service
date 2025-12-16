import asyncio
import sys
import os
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.actions.process_transcript_masker_action import ProcessTranscriptMaskerAction

def create_mock_re_verify_results():
    """สร้างข้อมูล mock สำหรับ re_verify_results"""
    return [
        {
            "detection_id": "det_001",
            "detection_type": "card_number",
            "original_text": "หกหกศูนย์สองศูนย์ศูนย์สองเก้าสี่สอง",
            "start_time": 51.44,
            "end_time": 64.0,
            "re_verify_result": {
                "recommendation": "PASS",
                "likely_category": "credit_debit_card",
                "reasoning": "ตรงตามรูปแบบบัตรเครดิต",
                "confidence": 0.98
            },
            "chunk_id": 0
        },
        {
            "detection_id": "det_002",
            "detection_type": "card_number",
            "original_text": "ห้าสองห้าหกหกแปดสองหนึ่งศูนย์เก้า",
            "start_time": 1194.11,
            "end_time": 1194.43,
            "re_verify_result": {
                "recommendation": "PASS",
                "likely_category": "credit_debit_card",
                "reasoning": "ตรงตามรูปแบบบัตรเครดิต",
                "confidence": 0.99
            },
            "chunk_id": 1
        },
        {
            "detection_id": "det_003",
            "detection_type": "card_number",
            "original_text": "หกแปดสองหนึ่ง",
            "start_time": 1198.75,
            "end_time": 1199.79,
            "re_verify_result": {
                "recommendation": "PASS",
                "likely_category": "credit_debit_card",
                "reasoning": "ตรงตามรูปแบบบัตรเครดิต",
                "confidence": 0.97
            },
            "chunk_id": 1
        },
        {
            "detection_id": "det_004",
            "detection_type": "expiration_date",
            "original_text": "ศูนย์สองทับสองเก้า",
            "start_time": 1211.85,
            "end_time": 1213.29,
            "re_verify_result": {
                "recommendation": "PASS",
                "likely_category": "expiration_date",
                "reasoning": "ตรงตามรูปแบบวันหมดอายุ",
                "confidence": 0.98
            },
            "chunk_id": 2
        },
        {
            "detection_id": "det_005",
            "detection_type": "card_number",
            "original_text": "หมายอนุญาตเลขที่หกหกศูนย์สองศูนย์ศูนย์สองเก้าสี่สอง",
            "start_time": 47.92,
            "end_time": 51.44,
            "re_verify_result": {
                "recommendation": "FAIL",
                "likely_category": "other",
                "reasoning": "เป็นหมายเลขอนุญาต ไม่ใช่บัตรเครดิต",
                "confidence": 0.95
            },
            "chunk_id": 0
        },
        {
            "detection_id": "det_006",
            "detection_type": "card_number",
            "original_text": "เบอร์หนึ่งเจ็ดห้าแปด",
            "start_time": 593.98,
            "end_time": 594.46,
            "re_verify_result": {
                "recommendation": "FAIL",
                "likely_category": "other",
                "reasoning": "เป็นเบอร์โทรศัพท์ ไม่ใช่บัตรเครดิต",
                "confidence": 0.92
            },
            "chunk_id": 3
        }
    ]

def create_mock_transcript():
    """สร้างข้อมูล mock สำหรับ transcript"""
    return {
        "transcript": [
            {
                "text": "สวัสดีครับ ผมชื่อพันธรรมาพิทักษ์พรค่ะ",
                "start": 0.0,
                "end": 5.0
            },
            {
                "text": "หมายอนุญาตเลขที่หกหกศูนย์สองศูนย์ศูนย์สองเก้าสี่สอง",
                "start": 47.92,
                "end": 51.44
            },
            {
                "text": "หกหกศูนย์สองศูนย์ศูนย์สองเก้าสี่สอง",
                "start": 51.44,
                "end": 64.0
            },
            {
                "text": "ห้าสองห้าหกหกแปดสองหนึ่งศูนย์เก้า",
                "start": 1194.11,
                "end": 1194.43
            },
            {
                "text": "หกแปดสองหนึ่ง",
                "start": 1198.75,
                "end": 1199.79
            },
            {
                "text": "ศูนย์สองทับสองเก้า",
                "start": 1211.85,
                "end": 1213.29
            },
            {
                "text": "เบอร์หนึ่งเจ็ดห้าแปด",
                "start": 593.98,
                "end": 594.46
            }
        ]
    }

def test_extract_pass_detections():
    """ทดสอบการแยก PASS detections จาก re_verify_results"""
    print("=" * 60)
    print("ทดสอบการแยก PASS detections จาก re_verify_results")
    print("=" * 60)
    
    # สร้าง masker action instance
    masker_action = ProcessTranscriptMaskerAction()
    
    # สร้างข้อมูล mock
    mock_re_verify_results = create_mock_re_verify_results()
    
    print(f"ข้อมูล re_verify_results ทั้งหมด: {len(mock_re_verify_results)} รายการ")
    print("\nรายละเอียด:")
    for i, result in enumerate(mock_re_verify_results, 1):
        rec = result.get('re_verify_result', {})
        print(f"  {i}. ID: {result['detection_id']}, Type: {result['detection_type']}, "
              f"Recommendation: {rec.get('recommendation', 'UNKNOWN')}, "
              f"Category: {rec.get('likely_category', 'UNKNOWN')}")
    
    # เรียกใช้ฟังก์ชัน _extract_pass_detections
    pass_detections = masker_action._extract_pass_detections(mock_re_verify_results)
    
    print(f"\nPASS detections ที่แยกได้: {len(pass_detections)} รายการ")
    print("\nรายละเอียด PASS detections:")
    for i, detection in enumerate(pass_detections, 1):
        print(f"  {i}. ID: {detection['id']}, Type: {detection['type']}, "
              f"Status: {detection['verification_status']}, "
              f"Category: {detection['likely_category']}, "
              f"Confidence: {detection['confidence']:.2f}")
        print(f"     Original Text: {detection['original_text']}")
        print(f"     Time Range: {detection['start_time']:.2f} - {detection['end_time']:.2f}")
    
    # ตรวจสอบผลลัพธ์
    expected_pass_count = 4  # det_001, det_002, det_003, det_004
    if len(pass_detections) == expected_pass_count:
        print(f"\n✅ ทดสอบผ่าน: พบ PASS detections จำนวน {len(pass_detections)} รายการ ตามที่คาดหวัง")
    else:
        print(f"\n❌ ทดสอบล้มเหลว: คาดหวัง {expected_pass_count} รายการ แต่พบ {len(pass_detections)} รายการ")
    
    # ตรวจสอบว่า detections ที่ได้มี recommendation = PASS จริง
    all_pass = all(d.get('verification_status') == 'PASS' for d in pass_detections)
    if all_pass:
        print("✅ ทดสอบผ่าน: ทุก detection มี verification_status = PASS")
    else:
        print("❌ ทดสอบล้มเหลว: มี detection ที่ไม่มี verification_status = PASS")
    
    return pass_detections

def test_masker_action_input():
    """ทดสอบการสร้าง input สำหรับ masker action"""
    print("\n" + "=" * 60)
    print("ทดสอบการสร้าง input สำหรับ masker action")
    print("=" * 60)
    
    # สร้าง masker action instance
    masker_action = ProcessTranscriptMaskerAction()
    
    # สร้างข้อมูล mock
    mock_transcript = create_mock_transcript()
    mock_re_verify_results = create_mock_re_verify_results()
    
    # สร้าง input สำหรับ masker action
    masker_input = {
        "transcript": mock_transcript,
        "re_verify_results": mock_re_verify_results
    }
    
    print("Input สำหรับ masker action:")
    print(f"  Transcript: {len(mock_transcript['transcript'])} segments")
    print(f"  Re-verify Results: {len(mock_re_verify_results)} detections")
    
    # แยก PASS detections
    pass_detections = masker_action._extract_pass_detections(mock_re_verify_results)
    print(f"  PASS Detections: {len(pass_detections)} detections")
    
    return masker_input, pass_detections

async def test_masker_action_execute():
    """ทดสอบการทำงานของ masker action (แต่ไม่รัน workflow)"""
    print("\n" + "=" * 60)
    print("ทดสอบการทำงานของ masker action (ไม่รัน workflow)")
    print("=" * 60)
    
    # สร้าง masker action instance
    masker_action = ProcessTranscriptMaskerAction()
    
    # สร้างข้อมูล mock
    mock_transcript = create_mock_transcript()
    mock_re_verify_results = create_mock_re_verify_results()
    
    # สร้าง input สำหรับ masker action
    masker_input = {
        "transcript": mock_transcript,
        "re_verify_results": mock_re_verify_results
    }
    
    print("เริ่มทดสอบ masker action...")
    
    try:
        # แยก PASS detections
        pass_detections = masker_action._extract_pass_detections(mock_re_verify_results)
        print(f"✅ แยก PASS detections สำเร็จ: {len(pass_detections)} รายการ")
        
        # แสดงข้อมูลที่จะส่งไปยัง masker workflow
        print("\nข้อมูลที่จะส่งไปยัง masker workflow:")
        for detection in pass_detections:
            print(f"  - ID: {detection['id']}, Type: {detection['type']}, "
                  f"Text: {detection['original_text']}, "
                  f"Time: {detection['start_time']:.2f}-{detection['end_time']:.2f}")
        
        print("\n✅ ทดสอบสำเร็จ: masker action สามารถแยก PASS detections ได้อย่างถูกต้อง")
        
    except Exception as e:
        print(f"\n❌ ทดสอบล้มเหลว: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("ทดสอบ ProcessTranscriptMaskerAction")
    print("=" * 60)
    
    # ทดสอบการแยก PASS detections
    test_extract_pass_detections()
    
    # ทดสอบการสร้าง input
    test_masker_action_input()
    
    # ทดสอบการทำงานของ masker action
    asyncio.run(test_masker_action_execute())