"""Specification comparison tool: compare vendor offers (KP) against requirements (TZ)."""

from typing import Dict, List, Any

def get_tools():
    from ouroboros.tools.registry import ToolEntry

    def spec_compare(ctx, *, requirements_text: str, offer_text: str) -> str:
        """
        Compare a technical offer (KP) against requirements (TZ).

        Args:
            requirements_text: Full text of the requirements specification (TZ).
                              Can be obtained via knowledge_read(topic='requirements-<project>').
            offer_text: Full text of the vendor's commercial offer (KP).
                       Usually read via xlsx_read or pdf_read.

        Returns:
            A structured markdown analysis containing:
            - Executive summary: complies / partially complies / does not comply
            - Compliance matrix (Parameter | Requirement | Offer | Status)
            - Critical deviations (any ❌ items)
            - Commercial summary (price, delivery, warranty, payment terms)
        """
        # Use the main model to perform the actual comparison. This tool returns a prompt template
        # that instructs the model how to structure the response. The agent will call this tool and then
        # the model will produce the final analysis in the requested format.

        prompt = f"""You are a procurement analyst. Compare the vendor's offer against the technical requirements.

## Technical Requirements (TZ)
```
{requirements_text}
```

## Vendor Offer (KP)
```
{offer_text}
```

Perform a line-by-line comparison for the following critical dimensions (extract from the texts):

1. **Hardware configuration** (GPU type, quantity, CPU, RAM, storage, networking)
2. **Performance parameters** (throughput, latency, capacity)
3. **Certifications and Operating System** (required OS, compliance)
4. **Warranty and support** (duration, SLA, on-site parts)
5. **Commercial terms** (price per unit, total price, delivery date, payment terms, currency)

For each parameter:
- If the offer meets or exceeds the requirement → mark with ✅
- If the offer is close but has minor deviations → mark with ⚠️
- If the offer fails to meet a requirement → mark with ❌ (CRITICAL)

Output format (strict markdown):

# Analysis of Vendor Offer

## Executive Summary
- Overall compliance: [✅ COMPLIES / ⚠️ PARTIAL / ❌ NON-COMPLIANT]
- Critical issues: [list of ❌ items, if any]

## Compliance Matrix

| Parameter | Requirement | Offer | Status |
|-----------|-------------|-------|--------|
| ... | ... | ... | ... |

## Critical Deviations
- ❌ [Describe each critical deviation and its risk]

## Commercial Summary
- **Unit price:** [...]
- **Total value:** [...]
- **Delivery:** [...]
- **Warranty:** [...]
- **Payment terms:** [...]"""

        # Return the prompt; the agent will forward it to the model as its next turn.
        return prompt

    return [
        ToolEntry(
            name="spec_compare",
            schema={
                "name": "spec_compare",
                "description": "Compare a technical offer (KP) against requirements (TZ). Returns a structured analysis prompt for the model to fill. Use after reading both documents with xlsx_read/pdf_read.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "requirements_text": {
                            "type": "string",
                            "description": "Full requirements specification text (TZ). Usually from knowledge base topic 'requirements-<project>'."
                        },
                        "offer_text": {
                            "type": "string",
                            "description": "Full vendor commercial offer text (KP). Usually extracted from an Excel/PDF file."
                        }
                    },
                    "required": ["requirements_text", "offer_text"]
                }
            },
            handler=spec_compare,
            is_code_tool=False,
            timeout_sec=120,
        )
    ]
