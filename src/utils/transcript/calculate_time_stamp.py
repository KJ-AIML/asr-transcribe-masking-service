def calculate_word_timing(masking_result, segments):
    """คำนวณเวลาเฉพาะคำที่เป็นตัวเลขจาก segment ด้วย word-level timestamps"""
    segment_ids = masking_result.get("segment_ids", [])
    original_text = masking_result.get("original_text", "")

    if not original_text:
        return {
            "start_time": masking_result.get("start_time"),
            "end_time": masking_result.get("end_time"),
        }

    original_text_normalized = original_text.replace(" ", "").strip()

    for segment in segments:
        if segment.get("id") in segment_ids and "words" in segment:
            words = segment.get("words", [])
            segment_text = " ".join([w.get("word", "") for w in words])
            segment_text_normalized = segment_text.replace(" ", "").strip()

            if original_text_normalized not in segment_text_normalized:
                continue

            first_word_idx = None
            last_word_idx = None
            accumulated_text = ""

            for i, word in enumerate(words):
                word_text = word.get("word", "")
                if not word_text:
                    continue

                if first_word_idx is None:
                    test_text = (accumulated_text + word_text).replace(" ", "")
                    if original_text_normalized.startswith(test_text):
                        first_word_idx = i
                    accumulated_text += word_text + " "
                else:
                    accumulated_text += word_text + " "
                    test_text = accumulated_text.replace(" ", "")

                    if original_text_normalized == test_text:
                        last_word_idx = i
                        break
                    elif original_text_normalized.startswith(test_text):
                        last_word_idx = i

            if first_word_idx is not None and last_word_idx is not None:
                start_time = words[first_word_idx].get("start")
                end_time = words[last_word_idx].get("end")

                if start_time is not None and end_time is not None:
                    return {
                        "start_time": start_time,
                        "end_time": end_time,
                    }

    return {
        "start_time": masking_result.get("start_time"),
        "end_time": masking_result.get("end_time"),
    }
