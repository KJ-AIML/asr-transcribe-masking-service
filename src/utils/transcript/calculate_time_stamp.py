def calculate_word_timing(masking_result, segments):
    """คำนวณเวลาเฉพาะคำที่เป็นตัวเลขจาก segment"""
    segment_ids = masking_result.get("segment_ids", [])
    original_text = masking_result.get("original_text", "")

    # หา segment ที่เกี่ยวข้อง
    for segment in segments:
        if segment.get("id") in segment_ids and "words" in segment:
            words = segment.get("words", [])

            # หาคำที่ตรงกับข้อความที่ต้องการ mask
            for i, word in enumerate(words):
                word_text = word.get("word", "")
                # ตรวจสอบว่าคำนี้เป็นส่วนหนึ่งของ original_text หรือไม่
                if original_text and word_text in original_text:
                    # คืนเวลาเฉพาะคำนั้น
                    return {
                        "start_time": word.get(
                            "start", masking_result.get("start_time")
                        ),
                        "end_time": word.get("end", masking_result.get("end_time")),
                    }

    # ถ้าไม่เจอคำที่ตรงกัน ใช้เวลาของ segment
    return {
        "start_time": masking_result.get("start_time"),
        "end_time": masking_result.get("end_time"),
    }
