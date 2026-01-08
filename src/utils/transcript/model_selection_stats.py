"""
Utils function for analyzing ASR model comparison results
to prepare data for choose_model_to_transcribe workflow
"""

from typing import Dict, Any
import pandas as pd
from datetime import datetime


def analyze_compare_results_for_model_selection(
    compare_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Analyze compare_results from ProcessWavFileAction to prepare data for choose_model workflow

    Args:
        compare_results: Dict containing comparison results for all chunks

    Returns:
        Dict with metrics, missing_examples, and row_summaries for model selection
    """
    if not compare_results:
        return {
            "metrics": {
                "total_chunks": 0,
                "typhoon_missing_context_count": 0,
                "pathumma_missing_context_count": 0,
                "pathumma_noise_missing_context_count": 0,
                "typhoon_avg_missing_items": 0.0,
                "pathumma_avg_missing_items": 0.0,
                "pathumma_noise_avg_missing_items": 0.0,
            },
            "missing_examples": [],
            "row_summaries": [],
        }

    # Convert compare_results to DataFrame-like structure for analysis
    rows = []
    for chunk_id, result in compare_results.items():
        if not result or not isinstance(result, dict):
            continue

        # Extract data from compare_result array
        compare_result = result.get("compare_result", [])
        if not compare_result or len(compare_result) == 0:
            continue

        first_result = compare_result[0]
        recommendations = first_result.get("recommendations", [])
        reasoning = first_result.get("reasoning", "")
        typhoon_baseline = first_result.get("typhoon_baseline", {})
        pathumma_vs_noise = first_result.get("pathumma_vs_noise", {})

        # Determine missing context flags from actual analysis data
        ty_missing = typhoon_baseline.get("has_missing_context", False)
        pa_missing = False  # Pathumma missing context determined from recommendations
        pn_missing = (
            False  # Pathumma_noise missing context determined from recommendations
        )

        # Check recommendations for pathumma/pathumma_noise issues
        for rec in recommendations:
            rec_lower = rec.lower()
            if "pathumma" in rec_lower and "noise" not in rec_lower:
                if "missing" in rec_lower or "incomplete" in rec_lower:
                    pa_missing = True
            elif "pathumma_noise" in rec_lower or (
                "noise" in rec_lower and "pathumma" in rec_lower
            ):
                if "missing" in rec_lower or "incomplete" in rec_lower:
                    pn_missing = True

        # Count missing items from actual analysis
        ty_missing_items = typhoon_baseline.get("missing_items", [])
        ty_missing_count = (
            len(ty_missing_items) if ty_missing_items else (1 if ty_missing else 0)
        )
        pa_missing_count = 1 if pa_missing else 0
        pn_missing_count = 1 if pn_missing else 0

        row = {
            "chunk_id": chunk_id,
            "ty_missing_context": ty_missing,
            "pa_missing_context": pa_missing,
            "pn_missing_context": pn_missing,
            "ty_missing_count": ty_missing_count,
            "pa_missing_count": pa_missing_count,
            "pn_missing_count": pn_missing_count,
            "recommendations": recommendations,
            "reasoning": reasoning,
            "typhoon_baseline": typhoon_baseline,
            "pathumma_vs_noise": pathumma_vs_noise,
        }
        rows.append(row)

    if not rows:
        return {
            "metrics": {
                "total_chunks": 0,
                "typhoon_missing_context_count": 0,
                "pathumma_missing_context_count": 0,
                "pathumma_noise_missing_context_count": 0,
                "typhoon_avg_missing_items": 0.0,
                "pathumma_avg_missing_items": 0.0,
                "pathumma_noise_avg_missing_items": 0.0,
            },
            "missing_examples": [],
            "row_summaries": [],
        }

    df = pd.DataFrame(rows)

    # Calculate metrics
    total = len(df)
    n_ty_missing = df["ty_missing_context"].sum()
    n_pa_missing = df["pa_missing_context"].sum()
    n_pn_missing = df["pn_missing_context"].sum()

    avg_ty_missing = (
        df[df["ty_missing_context"]]["ty_missing_count"].mean()
        if n_ty_missing > 0
        else 0.0
    )
    avg_pa_missing = (
        df[df["pa_missing_context"]]["pa_missing_count"].mean()
        if n_pa_missing > 0
        else 0.0
    )
    avg_pn_missing = (
        df[df["pn_missing_context"]]["pn_missing_count"].mean()
        if n_pn_missing > 0
        else 0.0
    )

    metrics = {
        "total_chunks": total,
        "typhoon_missing_context_count": int(n_ty_missing),
        "pathumma_missing_context_count": int(n_pa_missing),
        "pathumma_noise_missing_context_count": int(n_pn_missing),
        "typhoon_avg_missing_items": float(avg_ty_missing),
        "pathumma_avg_missing_items": float(avg_pa_missing),
        "pathumma_noise_avg_missing_items": float(avg_pn_missing),
    }

    # Create summary stats text (similar to POC)
    summary_stats_text = f"""
    รวม chunk ที่ประเมิน: {total}
    มี has_missing_context=True (Typhoon): {n_ty_missing}
    มี has_missing_context=True (Pathumma): {n_pa_missing}
    มี has_missing_context=True (Pathumma Noise): {n_pn_missing}
    ค่าเฉลี่ย missing_count (Typhoon): {avg_ty_missing:.2f}
    ค่าเฉลี่ย missing_count (Pathumma): {avg_pa_missing:.2f}
    ค่าเฉลี่ย missing_count (Pathumma Noise): {avg_pn_missing:.2f}
    """.strip()

    # Get missing examples (chunks with missing context)
    missing_examples = []
    missing_df = df[
        (df["ty_missing_context"])
        | (df["pa_missing_context"])
        | (df["pn_missing_context"])
    ]

    for _, row in missing_df.iterrows():
        example = {
            "chunk_id": row["chunk_id"],
            "ty_missing_context": bool(row["ty_missing_context"]),
            "pa_missing_context": bool(row["pa_missing_context"]),
            "pn_missing_context": bool(row["pn_missing_context"]),
            "ty_missing_count": int(row["ty_missing_count"]),
            "pa_missing_count": int(row["pa_missing_count"]),
            "pn_missing_count": int(row["pn_missing_count"]),
            "recommendations": row["recommendations"],
            "reasoning": row["reasoning"],
        }
        missing_examples.append(example)

    # Create row summaries for all chunks
    row_summaries = []
    for _, row in df.iterrows():
        summary = {
            "chunk_id": row["chunk_id"],
            "ty_missing_context": bool(row["ty_missing_context"]),
            "pa_missing_context": bool(row["pa_missing_context"]),
            "pn_missing_context": bool(row["pn_missing_context"]),
            "ty_missing_count": int(row["ty_missing_count"]),
            "pa_missing_count": int(row["pa_missing_count"]),
            "pn_missing_count": int(row["pn_missing_count"]),
            "recommendations": row["recommendations"],
            "reasoning": row["reasoning"],
        }
        row_summaries.append(summary)

    return {
        "metrics": metrics,
        "missing_examples": missing_examples,
        "row_summaries": row_summaries,
        "summary_stats_text": summary_stats_text,
    }


def prepare_choose_model_input(compare_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare input data for choose_model_to_transcribe workflow

    Args:
        compare_results: Dict containing comparison results for all chunks

    Returns:
        Dict formatted for agent_choose_model_to_transcribe.md input
    """
    # Extract actual chunk results from the "results" key
    actual_results = compare_results.get("results", {})

    analysis = analyze_compare_results_for_model_selection(actual_results)

    # Format according to agent_choose_model_to_transcribe.md expected input
    choose_model_input = {
        "metrics": analysis["metrics"],
        "missing_examples": analysis["missing_examples"],
        "row_summaries": analysis["row_summaries"],
        "analysis_timestamp": datetime.now().isoformat(),
        "total_chunks_processed": analysis["metrics"]["total_chunks"],
    }

    return choose_model_input
