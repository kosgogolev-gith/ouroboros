"""Specification comparison tool: compare vendor offers against stored baseline requirements."""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.tools.xlsx_reader import _xlsx_read as xlsx_read_impl, _resolve_path
from ouroboros.tools.pdf_tools import _pdf_read as pdf_read_impl

log = logging.getLogger(__name__)


def _load_requirements(ctx: ToolContext, project: str) -> str:
    """Load baseline requirements from knowledge base."""
    try:
        # Use the knowledge_read tool through the tool context if available
        # or directly call the function if we can import it
        from ouroboros.tools.knowledge_tools import knowledge_read_impl
        return knowledge_read_impl(ctx, topic=f"requirements-{project}")
    except ImportError:
        # Fallback: try to read from Drive knowledge base manually
        kb_path = ctx.drive_path(f"knowledge/requirements-{project}.md")
        if kb_path.exists():
            return kb_path.read_text(encoding="utf-8")
        return None


def _parse_requirements_text(text: str) -> Dict[str, Any]:
    """Parse requirements text into a structured dict of {parameter: {expected, critical}}."""
    requirements: Dict[str, Any] = {}
    current_section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Detect section headers (all caps or ends with colon)
        if line.isupper() or line.endswith(":"):
            current_section = line.rstrip(":").lower()
            requirements[current_section] = {}
            continue
        # Parse key-value pairs like "GPU: HGX H200 141GB" or "RAM: ≥ 2 TB"
        if ":" in line and current_section:
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            # Determine criticality based on wording
            critical = any(word in val for word in ["≥", "≥ ", ">= ", "minimum", "min", "required", "must", "mandatory"])
            requirements[current_section][key] = {
                "expected": val,
                "critical": critical,
                "section": current_section,
            }
    return requirements


def _parse_vendor_text(text: str) -> Dict[str, Any]:
    """Parse vendor offer text into structured dict."""
    vendor_data: Dict[str, Any] = {}
    current_section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isupper() or line.endswith(":"):
            current_section = line.rstrip(":").lower()
            vendor_data[current_section] = {}
            continue
        if ":" in line and current_section:
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            vendor_data[current_section][key] = val
    return vendor_data


def _compare_parameter(req_val: str, ven_val: str) -> Tuple[str, str]:
    """Compare a single requirement vs vendor value. Returns (status, note)."""
    req_norm = req_val.lower().replace(" ", "").replace("≥", "").replace(">=", "").replace("gb", "").replace("tb", "")
    ven_norm = ven_val.lower().replace(" ", "").replace("gb", "").replace("tb", "")
    # Exact match or vendor exceeds requirement
    if req_val == ven_val or req_norm == ven_norm:
        return "✅", "Matches"
    # Check if vendor meets minimum (with >= or similar)
    if "≥" in req_val or ">=" in req_val:
        try:
            # Extract numeric part
            import re
            m = re.search(r"[\d.]+", req_val)
            if m:
                req_num = float(m.group())
                ven_match = re.search(r"[\d.]+", ven_val)
                if ven_match:
                    ven_num = float(ven_match.group())
                    if ven_num >= req_num:
                        return "✅", f"Exceeds requirement ({ven_val})"
                    else:
                        return "❌", f"Below minimum"
        except Exception:
            pass
    return "⚠️", "Potential mismatch"


def _generate_report(requirements: Dict, vendor_data: Dict) -> Dict[str, Any]:
    """Generate compliance matrix and summary."""
    report = {
        "compliance_matrix": [],
        "critical_deviations": [],
        "commercial_summary": {},
        "overall_status": "✅",
    }
    # Track status distribution
    status_counts = {"✅": 0, "⚠️": 0, "❌": 0}
    # Compare each requirement section
    for section, req_section in requirements.items():
        if section not in vendor_data:
            report["compliance_matrix"].append({
                "section": section,
                "parameter": "ALL",
                "expected": "N/A (section missing in vendor offer)",
                "vendor": "—",
                "status": "❌",
                "note": "Entire section missing",
            })
            status_counts["❌"] += 1
            report["overall_status"] = "❌"
            continue
        ven_section = vendor_data[section]
        for param, meta in req_section.items():
            ven_val = ven_section.get(param, "—")
            status, note = _compare_parameter(meta["expected"], ven_val)
            status_counts[status] += 1
            report["compliance_matrix"].append({
                "section": section,
                "parameter": param,
                "expected": meta["expected"],
                "vendor": ven_val,
                "status": status,
                "note": note,
            })
            if meta["critical"] and status in ("⚠️", "❌"):
                report["critical_deviations"].append({
                    "section": section,
                    "parameter": param,
                    "expected": meta["expected"],
                    "vendor": ven_val,
                    "status": status,
                })
    # Commercial summary: price, quantity, warranty, delivery
    # Assume vendor_data may have top-level keys
    top_keys = ["price", "total", "quantity", "warranty", "delivery", "lead time"]
    for key in top_keys:
        if key in vendor_data:
            report["commercial_summary"][key] = vendor_data[key]
    # Determine overall status: if any ❌ -> overall ❌; else if any ⚠️ -> overall ⚠️; else ✅
    if status_counts["❌"] > 0:
        report["overall_status"] = "❌"
    elif status_counts["⚠️"] > 0:
        report["overall_status"] = "⚠️"
    else:
        report["overall_status"] = "✅"
    return report


def _format_report(report: Dict) -> str:
    """Convert report dict to human-readable text."""
    lines = []
    lines.append(f"# Specification Comparison Report")
    lines.append(f"**Overall Status:** {report['overall_status']}")
    lines.append("")
    # Summary
    lines.append("## Summary")
    lines.append(f"- ✅ Compliant: {sum(1 for r in report['compliance_matrix'] if r['status']=='✅')}")
    lines.append(f"- ⚠️ Warnings: {sum(1 for r in report['compliance_matrix'] if r['status']=='⚠️')}")
    lines.append(f"- ❌ Non-compliant: {sum(1 for r in report['compliance_matrix'] if r['status']=='❌')}")
    lines.append("")
    # Critical deviations
    if report["critical_deviations"]:
        lines.append("## ⚠️ Critical Deviations")
        for d in report["critical_deviations"]:
            lines.append(f"- **{d['section']}/{d['parameter']}**: expected {d['expected']}, got {d['vendor']} [{d['status']}]")
        lines.append("")
    # Commercial summary
    if report["commercial_summary"]:
        lines.append("## Commercial Terms")
        for k, v in report["commercial_summary"].items():
            lines.append(f"- {k.capitalize()}: {v}")
        lines.append("")
    # Compliance matrix (detailed)
    lines.append("## Compliance Matrix")
    # Table header
    lines.append("| Section | Parameter | Expected | Vendor | Status | Note |")
    lines.append("|---------|-----------|----------|--------|--------|------|")
    for row in report["compliance_matrix"]:
        lines.append(f"| {row['section']} | {row['parameter']} | {row['expected']} | {row['vendor']} | {row['status']} | {row['note']} |")
    return "\n".join(lines)


def _spec_compare(ctx: ToolContext, vendor_path: str, baseline_project: str, baseline_text_override: str = "") -> str:
    """Compare a vendor offer (Excel/PDF) against stored baseline requirements.

    Args:
        vendor_path: Path to vendor offer file (XLSX or PDF).
        baseline_project: Project key (e.g., 'h200' or 'b200x8') to load from knowledge base.
        baseline_text_override: Optional raw text of requirements to use instead of KB.

    Returns:
        A structured report with compliance matrix, critical deviations, and commercial summary.
    """
    # 1. Load baseline requirements text
    if baseline_text_override:
        baseline_text = baseline_text_override
    else:
        baseline_text = _load_requirements(ctx, baseline_project)
        if not baseline_text:
            return f"\u26a0\ufe0f Baseline requirements for project '{baseline_project}' not found in knowledge base. Please save them first using requirements_save or knowledge_write."
    # 2. Parse requirements
    requirements = _parse_requirements_text(baseline_text)
    if not requirements:
        return "\u26a0\ufe0f Failed to parse baseline requirements. Ensure they are in key: value format with section headers."

    # 3. Read vendor document
    file_path = _resolve_path(ctx, vendor_path)
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        vendor_text = xlsx_read_impl(ctx, vendor_path)
    elif suffix == ".pdf":
        vendor_text = pdf_read_impl(ctx, vendor_path)
    else:
        return f"\u26a0\ufe0f Unsupported file format: {suffix}. Use XLSX or PDF."

    if vendor_text.startswith("⚠️") or vendor_text.startswith("❌"):
        return vendor_text  # Propagate read error

    # 4. Parse vendor data
    vendor_data = _parse_vendor_text(vendor_text)
    if not vendor_data:
        return "\u26a0\ufe0f Failed to parse vendor document. Check format."

    # 5. Compare and generate report
    report = _generate_report(requirements, vendor_data)
    return _format_report(report)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("spec_compare", {
            "name": "spec_compare",
            "description": (
                "Compare a vendor commercial offer (Excel/PDF) against stored baseline requirements. "
                "Loads requirements from knowledge base (requirements-h200, requirements-b200x8). "
                "Generates compliance matrix with ✅/⚠️/❌, highlights critical deviations, and summarizes commercial terms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor_path": {
                        "type": "string",
                        "description": (
                            "Path to vendor offer file. Absolute or relative to Drive root."
                        ),
                    },
                    "baseline_project": {
                        "type": "string",
                        "description": (
                            "Project key for baseline requirements: 'h200' or 'b200x8'. "
                            "Corresponds to knowledge base topic 'requirements-{project}'."
                        ),
                        "enum": ["h200", "b200x8"],
                    },
                    "baseline_text_override": {
                        "type": "string",
                        "description": (
                            "Optional raw baseline requirements text to use instead of knowledge base."
                        ),
                    },
                },
                "required": ["vendor_path", "baseline_project"],
            },
        }, _spec_compare),
    ]
