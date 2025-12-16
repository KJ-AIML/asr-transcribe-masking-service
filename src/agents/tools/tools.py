from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from src.agents.schemas.types import ContextExtensionArgs, DetectionsInRangeArgs, OriginalTextRangeArgs
from src.utils.transcript.chunk_transcript import chunk_transcript
from src.utils.transcript.prase_transcript import parse_transcription
from src.config.logs_config import get_logger

logger = get_logger(__name__)

@tool(args_schema=ContextExtensionArgs)
def get_context_extension(
    base_start_time: float,
    direction: str = "backward",
    duration: float = 50.0,
    transcript_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    ดึงข้อมูล context เพิ่มเติมจากช่วงเวลาที่ระบุ
    
    Args:
        base_start_time: เวลาเริ่มต้นของ chunk ปัจจุบัน (วินาที)
        direction: "backward" (ดึงข้อมูลย้อนหลัง) หรือ "forward" (ดึงข้อมูลถัดไป)
        duration: ระยะเวลาที่ต้องการดึงเพิ่ม (วินาที)
        transcript_data: ข้อมูล transcript แบบ JSON
    
    Returns:
        Dict: ข้อมูล context ที่ดึงมาได้
    """
    try:
        if not transcript_data:
            return {"error": "No transcript data provided"}
        
        # คำนวณช่วงเวลาที่ต้องการ
        if direction == "backward":
            start_time = max(0, base_start_time - duration)
            end_time = base_start_time
        elif direction == "forward":
            start_time = base_start_time
            end_time = base_start_time + duration
        else:
            return {"error": "Invalid direction. Use 'backward' or 'forward'"}
        
        # สร้าง chunk จากช่วงเวลาที่ต้องการ
        context_chunk = chunk_transcript(
            json_data=transcript_data,
            chunk_duration=end_time - start_time,
            overlap_duration=0.0,
            include_original_text=True
        )
        
        # กรองเฉพาะส่วนที่อยู่ในช่วงเวลาที่ต้องการ
        filtered_segments = []
        filtered_words = []
        
        for segment in context_chunk["chunks"][0]["segments"]:
            if segment["start"] >= start_time and segment["end"] <= end_time:
                filtered_segments.append(segment)
        
        for word in context_chunk["chunks"][0]["words"]:
            if word["start"] >= start_time and word["end"] <= end_time:
                filtered_words.append(word)
        
        # สร้างข้อความจาก segments ที่กรองแล้ว
        context_text = ""
        if filtered_segments:
            context_text = "\n".join([
                f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
                for seg in filtered_segments
            ])
        
        return {
            "success": True, 
            "context_text": context_text, 
            "segments": filtered_segments, 
            "words": filtered_words, 
            "time_range": {"start": start_time, "end": end_time, 
            "duration": end_time - start_time}, 
            "direction": direction
            }
        
    except Exception as e:
        logger.error(f"Error in get_context_extension: {e}")
        return {"error": str(e)}

@tool(args_schema=DetectionsInRangeArgs)
def get_detections_in_range(
    start_time: float,
    end_time: float,
    detections_data: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    ดึงข้อมูล detections ในช่วงเวลาที่ระบุ
    
    Args:
        start_time: เวลาเริ่มต้น (วินาที)
        end_time: เวลาสิ้นสุด (วินาที)
        detections_data: รายการ detections ทั้งหมด
    
    Returns:
        Dict: ข้อมูล detections ที่อยู่ในช่วงเวลาที่ระบุ
    """
    try:
        if not detections_data:
            return {"error": "No detections data provided"}
        
        filtered_detections = []
        
        for detection in detections_data:
            # ตรวจสอบว่า detection อยู่ในช่วงเวลาที่ต้องการหรือไม่
            det_start = detection.get("start_time", 0)
            det_end = detection.get("end_time", 0)
            
            # ตรวจสอบการซ้อนทับกับช่วงเวลา
            if det_start < end_time and det_end > start_time:
                filtered_detections.append(detection)
        
        return {
            "success": True, 
            "detections": filtered_detections, 
            "count": len(filtered_detections), 
            "time_range": {"start": start_time, 
            "end": end_time, 
            "duration": end_time - start_time}
            }
        
    except Exception as e:
        logger.error(f"Error in get_detections_in_range: {e}")
        return {"error": str(e)}

@tool(args_schema=OriginalTextRangeArgs)
def get_original_text_range(
    start_time: float,
    end_time: float,
    transcript_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    ดึงข้อความต้นฉบับในช่วงเวลาที่ระบุ
    
    Args:
        start_time: เวลาเริ่มต้น (วินาที)
        end_time: เวลาสิ้นสุด (วินาที)
        transcript_data: ข้อมูล transcript แบบ JSON
    
    Returns:
        Dict: ข้อความต้นฉบับในช่วงเวลาที่ระบุ
    """
    try:
        if not transcript_data:
            return {"error": "No transcript data provided"}
        
        # สร้าง chunk จากช่วงเวลาที่ต้องการ
        original_chunk = chunk_transcript(
            json_data=transcript_data,
            chunk_duration=end_time - start_time,
            overlap_duration=0.0,
            include_original_text=True
        )
        
        # กรองเฉพาะส่วนที่อยู่ในช่วงเวลาที่ต้องการ
        filtered_segments = []
        filtered_words = []
        
        for segment in original_chunk["chunks"][0]["segments"]:
            if segment["start"] >= start_time and segment["end"] <= end_time:
                filtered_segments.append(segment)
        
        for word in original_chunk["chunks"][0]["words"]:
            if word["start"] >= start_time and word["end"] <= end_time:
                filtered_words.append(word)
        
        # สร้างข้อความจาก segments ที่กรองแล้ว
        original_text = ""
        if filtered_segments:
            original_text = "\n".join([
                f"[{seg['start']:.2f} --> {seg['end']:.2f}] [{seg['channel']}]: {seg['text']}"
                for seg in filtered_segments
            ])
        
        return {"success": True, "original_text": original_text, "segments": filtered_segments, "words": filtered_words, "time_range": {"start": start_time, "end": end_time, "duration": end_time - start_time}}
        
    except Exception as e:
        logger.error(f"Error in get_original_text_range: {e}")
        return {"error": str(e)}