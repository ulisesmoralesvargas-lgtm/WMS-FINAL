import os
from collections import Counter
from typing import Any

import requests
from google import genai
from google.genai import types


API_URL = (
    os.getenv("API_URL")
    or os.getenv("API_BASE_URL")
    or "https://inventory-2-271456327495.northamerica-south1.run.app"
).rstrip("/")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


SYSTEM_INSTRUCTION = """
You are the read-only Gemini Inventory Assistant for an asset management system.

Rules:
1. You are read-only.
2. Never modify, create, delete, transfer, check out, or check in assets.
3. Never write SQL.
4. Never ask for or reveal database credentials.
5. Only answer inventory questions using approved tool results.
6. Do not invent counts, campuses, departments, asset IDs, statuses, or values.
7. If data is unavailable, say that the current endpoint does not provide it.
8. When scan compliance is low, explain that many assets may simply not have been scanned yet.
"""


def _api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{API_URL}{path}"
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _limit_payload(data: Any, max_records: int = 25) -> Any:
    if isinstance(data, list):
        return {
            "records": data[:max_records],
            "records_returned": min(len(data), max_records),
            "records_available_in_response": len(data),
            "truncated": len(data) > max_records,
        }

    if isinstance(data, dict):
        cleaned = dict(data)

        for key in [
            "assets",
            "items",
            "results",
            "records",
            "exceptions",
            "tickets",
            "transfers",
            "data",
        ]:
            value = cleaned.get(key)

            if isinstance(value, list):
                cleaned[key] = value[:max_records]
                cleaned[f"{key}_returned"] = min(len(value), max_records)
                cleaned[f"{key}_available_in_response"] = len(value)
                cleaned[f"{key}_truncated"] = len(value) > max_records

        return cleaned

    return data


def get_dashboard_stats() -> dict[str, Any]:
    """Get high-level dashboard KPIs."""
    return {
        "endpoint": "/dashboard/stats",
        "data": _limit_payload(_api_get("/dashboard/stats")),
    }


def get_reports_summary() -> dict[str, Any]:
    """Get the reports summary."""
    return {
        "endpoint": "/reports/summary",
        "data": _limit_payload(_api_get("/reports/summary")),
    }


def get_scan_compliance_report() -> dict[str, Any]:
    """Get scan compliance information."""
    return {
        "endpoint": "/reports/scan-compliance",
        "data": _limit_payload(_api_get("/reports/scan-compliance")),
    }


def get_audit_exceptions_report() -> dict[str, Any]:
    """Get audit exceptions."""
    return {
        "endpoint": "/reports/audit-exceptions",
        "data": _limit_payload(_api_get("/reports/audit-exceptions")),
    }


def get_maintenance_tickets() -> dict[str, Any]:
    """Get maintenance ticket information."""
    return {
        "endpoint": "/maintenance",
        "data": _limit_payload(_api_get("/maintenance")),
    }


def get_transfers() -> dict[str, Any]:
    """Get asset transfer information."""
    return {
        "endpoint": "/transfers",
        "data": _limit_payload(_api_get("/transfers")),
    }


def _find_records(data: Any) -> list[dict[str, Any]]:
    """
    Find a list of records inside a JSON response.
    Works with responses like:
    - [ {...}, {...} ]
    - {"exceptions": [ ... ]}
    - {"assets": [ ... ]}
    - {"data": [ ... ]}
    - {"items": [ ... ]}
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ["exceptions", "assets", "items", "records", "results", "data"]:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _first_value(record: dict[str, Any], possible_keys: list[str]) -> str:
    for key in possible_keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "Unknown"


def get_location_risk_summary() -> dict[str, Any]:
    """
    Summarize audit exceptions by campus/location and status.

    Use this for questions like:
    - Which campuses have the most risk?
    - Which locations need the most attention?
    - Where are most audit issues happening?
    """
    raw = _api_get("/reports/audit-exceptions")
    records = _find_records(raw)

    campus_keys = [
        "sede",
        "campus",
        "Campus",
        "campus_name",
        "Campus Name",
        "location",
        "Location",
        "site",
        "Site",
    ]

    department_keys = [
        "departamento",
        "department",
        "Department",
        "dept",
        "Dept",
    ]

    status_keys = [
        "estatus",
        "status",
        "Status",
        "asset_status",
        "Asset Status",
    ]

    campus_counts = Counter()
    department_counts = Counter()
    status_counts = Counter()

    examples_by_campus: dict[str, list[dict[str, Any]]] = {}

    for record in records:
        campus = _first_value(record, campus_keys)
        department = _first_value(record, department_keys)
        status = _first_value(record, status_keys)

        campus_counts[campus] += 1
        department_counts[department] += 1
        status_counts[status] += 1

        if campus not in examples_by_campus:
            examples_by_campus[campus] = []

        if len(examples_by_campus[campus]) < 5:
            examples_by_campus[campus].append(record)

    return {
        "endpoint": "/reports/audit-exceptions",
        "total_audit_exception_records_analyzed": len(records),
        "top_campuses_or_locations": campus_counts.most_common(10),
        "top_departments": department_counts.most_common(10),
        "status_breakdown": status_counts.most_common(10),
        "sample_records_by_top_location": {
            campus: examples_by_campus.get(campus, [])
            for campus, _count in campus_counts.most_common(5)
        },
        "note": (
            "This summary is calculated from the audit exceptions report. "
            "Higher counts mean more audit attention is needed in that campus or location."
        ),
    }


def get_department_audit_summary() -> dict[str, Any]:
    """
    Summarize audit exceptions by department.

    Use this for questions like:
    - Which departments have the most audit issues?
    - Which departments should be prioritized?
    """
    raw = _api_get("/reports/audit-exceptions")
    records = _find_records(raw)

    department_keys = [
        "departamento",
        "department",
        "Department",
        "dept",
        "Dept",
    ]

    campus_keys = [
        "campus",
        "Campus",
        "campus_name",
        "Campus Name",
        "location",
        "Location",
    ]

    department_counts = Counter()
    department_campus_counts: dict[str, Counter] = {}

    for record in records:
        department = _first_value(record, department_keys)
        campus = _first_value(record, campus_keys)

        department_counts[department] += 1

        if department not in department_campus_counts:
            department_campus_counts[department] = Counter()

        department_campus_counts[department][campus] += 1

    return {
        "endpoint": "/reports/audit-exceptions",
        "total_audit_exception_records_analyzed": len(records),
        "top_departments": department_counts.most_common(10),
        "top_locations_by_department": {
            department: campus_counter.most_common(5)
            for department, campus_counter in department_campus_counts.items()
        },
        "note": (
            "This summary is calculated from the audit exceptions report. "
            "Higher counts mean the department has more assets requiring audit attention."
        ),
    }




def ask_inventory_assistant(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    message = message.strip()

    if not message:
        return "Please enter a question about the inventory."

    recent_history = history[-6:] if history else []

    history_text = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')[:1000]}"
        for item in recent_history
    )

    prompt = f"""
Recent conversation:
{history_text or "No previous conversation."}

Current user question:
{message}
"""

    try:
        with genai.Client() as client:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=[
                        get_dashboard_stats,
                        get_reports_summary,
                        get_scan_compliance_report,
                        get_audit_exceptions_report,
                        get_location_risk_summary,
                        get_department_audit_summary,
                        get_maintenance_tickets,
                        get_transfers,
                    ],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        maximum_remote_calls=5
                    ),
                    temperature=0.1,
                    max_output_tokens=900,
                ),
            )

        answer = (response.text or "").strip()

        if not answer:
            return "I could not generate an answer from the available inventory data."

        return answer

    except requests.HTTPError as exc:
        return f"I could not retrieve one of the inventory reports. API error: {exc}"

    except requests.RequestException:
        return "I could not connect to the inventory API right now."

    except Exception as exc:
        return (
            "The Gemini Inventory Assistant is temporarily unavailable. "
            f"Technical detail: {type(exc).__name__}"
        )
