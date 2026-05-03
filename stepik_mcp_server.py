#!/usr/bin/env python3
"""Stepik MCP Server — manage courses, sections, lessons, and steps via Stepik API."""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

CLIENT_ID = os.environ.get("STEPIK_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("STEPIK_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("STEPIK_CLIENT_ID and STEPIK_CLIENT_SECRET environment variables are required")

BASE_URL = "https://stepik.org/api"
TOKEN_URL = "https://stepik.org/oauth2/token/"

mcp = FastMCP(
    "stepik",
    instructions=(
        "Stepik MCP Server — manage online courses on Stepik.\n\n"
        "Hierarchy: Course → Sections → Units → Lessons → Steps.\n"
        "- Use stepik_list_courses to find your courses.\n"
        "- Use stepik_get_course to inspect a course.\n"
        "- Use stepik_get_sections to list sections (modules) of a course.\n"
        "- Use stepik_get_lessons to list lessons in a section.\n"
        "- Use stepik_get_steps to list steps in a lesson (returns step-source IDs for editing).\n"
        "- Steps are the actual content: text, choice, matching, string, etc.\n"
        "- Use stepik_create_* in order: course → section → lesson → unit → step.\n"
        "- Use stepik_update_* or stepik_delete_step to modify existing content.\n"
        "Note: lesson titles are limited to 64 characters on Stepik."
    ),
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
_token_cache: dict[str, Any] = {"token": None, "expires": 0}


def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    auth_header = base64.b64encode(credentials).decode()

    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    token = result.get("access_token", "")
    if not token:
        raise RuntimeError(f"Auth failed: {result}")

    expires_in = result.get("expires_in", 3600)
    _token_cache["token"] = token
    _token_cache["expires"] = time.time() + expires_in - 60
    return token


def _api(method: str, path: str, body: Any = None, params: dict | list | None = None) -> Any:
    token = _get_token()
    url = f"{BASE_URL}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}: {body_text}") from e


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

@mcp.tool()
def stepik_list_courses(page: int = 1) -> str:
    """List your own courses on Stepik (as instructor)."""
    result = _api("GET", "courses", params={"is_my_own": "true", "page": page})
    courses = result.get("courses", [])
    if not courses:
        return "No courses found."
    lines = []
    for c in courses:
        lines.append(
            f"ID={c['id']} | {c['title']} | "
            f"published={c.get('is_enabled', False)} | "
            f"learners={c.get('learners_count', 0)}"
        )
    meta = result.get("meta", {})
    lines.append(f"\nPage {meta.get('page', 1)}/{meta.get('pages_count', 1)}")
    return "\n".join(lines)


@mcp.tool()
def stepik_get_course(course_id: int) -> str:
    """Get detailed info about a course by ID."""
    result = _api("GET", f"courses/{course_id}")
    courses = result.get("courses", [])
    if not courses:
        return f"Course {course_id} not found."
    c = courses[0]
    return json.dumps({
        "id": c["id"],
        "title": c["title"],
        "summary": c.get("summary", ""),
        "workload": c.get("workload", ""),
        "is_enabled": c.get("is_enabled", False),
        "learners_count": c.get("learners_count", 0),
        "certificate_footer": c.get("certificate_footer", ""),
        "url": f"https://stepik.org/course/{c['id']}",
        "edit_url": f"https://stepik.org/course/{c['id']}/edit",
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_create_course(
    title: str,
    summary: str = "",
    workload: str = "",
    target_audience: str = "",
    requirements: str = "",
) -> str:
    """Create a new course on Stepik (created as draft)."""
    body = {
        "course": {
            "title": title,
            "summary": summary,
            "workload": workload,
            "target_audience": target_audience,
            "requirements": requirements,
            "is_enabled": False,
        }
    }
    result = _api("POST", "courses", body)
    c = result["courses"][0]
    return f"Course created: ID={c['id']} — {c['title']}\nEdit: https://stepik.org/course/{c['id']}/edit"


@mcp.tool()
def stepik_update_course(
    course_id: int,
    title: str | None = None,
    summary: str | None = None,
    workload: str | None = None,
    target_audience: str | None = None,
    requirements: str | None = None,
    is_enabled: bool | None = None,
    certificate_footer: str | None = None,
) -> str:
    """Update course metadata. Only provided fields are changed."""
    patch: dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
    if summary is not None:
        patch["summary"] = summary
    if workload is not None:
        patch["workload"] = workload
    if target_audience is not None:
        patch["target_audience"] = target_audience
    if requirements is not None:
        patch["requirements"] = requirements
    if is_enabled is not None:
        patch["is_enabled"] = is_enabled
    if certificate_footer is not None:
        patch["certificate_footer"] = certificate_footer

    if not patch:
        return "Nothing to update."

    result = _api("PUT", f"courses/{course_id}", {"course": patch})
    c = result["courses"][0]
    return f"Course updated: ID={c['id']} — {c['title']}"


@mcp.tool()
def stepik_publish_course(course_id: int) -> str:
    """Publish a course (make it visible to learners)."""
    result = _api("PUT", f"courses/{course_id}", {"course": {"is_enabled": True}})
    c = result["courses"][0]
    return f"Course published: https://stepik.org/course/{c['id']}"


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

@mcp.tool()
def stepik_get_sections(course_id: int) -> str:
    """List all sections (modules) in a course."""
    course_result = _api("GET", f"courses/{course_id}")
    courses = course_result.get("courses", [])
    if not courses:
        return f"Course {course_id} not found."
    section_ids = courses[0].get("sections", [])
    if not section_ids:
        return f"No sections found in course {course_id}."
    result = _api("GET", "sections", params=[("ids[]", sid) for sid in section_ids])
    sections = result.get("sections", [])
    if not sections:
        return f"No sections found in course {course_id}."
    lines = []
    for s in sorted(sections, key=lambda x: x.get("position", 0)):
        lines.append(f"ID={s['id']} | pos={s['position']} | {s['title']}")
    return "\n".join(lines)


@mcp.tool()
def stepik_create_section(course_id: int, title: str, position: int = 1) -> str:
    """Create a section (module) in a course."""
    body = {
        "section": {
            "course": course_id,
            "title": title,
            "position": position,
            "required_percent": 100,
        }
    }
    result = _api("POST", "sections", body)
    s = result["sections"][0]
    return f"Section created: ID={s['id']} — {s['title']} (pos={s['position']})"


@mcp.tool()
def stepik_update_section(section_id: int, title: str | None = None, position: int | None = None) -> str:
    """Update a section title or position."""
    patch: dict[str, Any] = {"id": section_id}
    if title is not None:
        patch["title"] = title
    if position is not None:
        patch["position"] = position
    result = _api("PUT", f"sections/{section_id}", {"section": patch})
    s = result["sections"][0]
    return f"Section updated: ID={s['id']} — {s['title']}"


@mcp.tool()
def stepik_delete_section(section_id: int) -> str:
    """Delete a section by ID."""
    _api("DELETE", f"sections/{section_id}")
    return f"Section {section_id} deleted."


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------

@mcp.tool()
def stepik_get_lessons(section_id: int) -> str:
    """List lessons in a section (via units)."""
    section_result = _api("GET", f"sections/{section_id}")
    sections = section_result.get("sections", [])
    if not sections:
        return f"Section {section_id} not found."
    unit_ids = sections[0].get("units", [])
    if not unit_ids:
        return f"No lessons in section {section_id}."

    units_result = _api("GET", "units", params=[("ids[]", uid) for uid in unit_ids])
    units = units_result.get("units", [])
    if not units:
        return f"No lessons in section {section_id}."

    lesson_ids = [u["lesson"] for u in units]
    lessons_result = _api("GET", "lessons", params=[("ids[]", lid) for lid in lesson_ids])
    lessons_by_id = {l["id"]: l for l in lessons_result.get("lessons", [])}

    lines = []
    for u in sorted(units, key=lambda x: x.get("position", 0)):
        l = lessons_by_id.get(u["lesson"], {})
        lines.append(
            f"unit={u['id']} lesson={u['lesson']} pos={u['position']} | {l.get('title', '?')}"
        )
    return "\n".join(lines)


@mcp.tool()
def stepik_get_lesson(lesson_id: int) -> str:
    """Get lesson details."""
    result = _api("GET", f"lessons/{lesson_id}")
    lessons = result.get("lessons", [])
    if not lessons:
        return f"Lesson {lesson_id} not found."
    l = lessons[0]
    return json.dumps({
        "id": l["id"],
        "title": l["title"],
        "steps_count": l.get("steps_count", 0),
        "is_public": l.get("is_public", False),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_create_lesson(title: str, is_public: bool = False) -> str:
    """Create a lesson. Title max 64 chars. Returns lesson ID."""
    title = title[:64]
    body = {"lesson": {"title": title, "is_public": is_public}}
    result = _api("POST", "lessons", body)
    l = result["lessons"][0]
    return f"Lesson created: ID={l['id']} — {l['title']}"


@mcp.tool()
def stepik_update_lesson(lesson_id: int, title: str | None = None, is_public: bool | None = None) -> str:
    """Update lesson title or visibility."""
    patch: dict[str, Any] = {"id": lesson_id}
    if title is not None:
        patch["title"] = title[:64]
    if is_public is not None:
        patch["is_public"] = is_public
    result = _api("PUT", f"lessons/{lesson_id}", {"lesson": patch})
    l = result["lessons"][0]
    return f"Lesson updated: ID={l['id']} — {l['title']}"


@mcp.tool()
def stepik_delete_lesson(lesson_id: int) -> str:
    """Delete a lesson by ID."""
    _api("DELETE", f"lessons/{lesson_id}")
    return f"Lesson {lesson_id} deleted."


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

@mcp.tool()
def stepik_create_unit(section_id: int, lesson_id: int, position: int = 1) -> str:
    """Attach a lesson to a section (creates a unit). Do this after stepik_create_lesson."""
    body = {"unit": {"section": section_id, "lesson": lesson_id, "position": position}}
    result = _api("POST", "units", body)
    u = result["units"][0]
    return f"Unit created: ID={u['id']} (section={section_id}, lesson={lesson_id}, pos={position})"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _get_step_source(step_id: int) -> dict[str, Any]:
    """Fetch step-source by step ID. Returns the step-source object."""
    result = _api("GET", f"step-sources/{step_id}")
    sources = result.get("step-sources", [])
    if not sources:
        raise RuntimeError(f"Step-source for step {step_id} not found.")
    return sources[0]


@mcp.tool()
def stepik_get_steps(lesson_id: int) -> str:
    """List all steps in a lesson. Returns step IDs (use these for update/delete operations)."""
    result = _api("GET", "steps", params={"lesson": lesson_id})
    steps = result.get("steps", [])
    if not steps:
        return f"No steps in lesson {lesson_id}."
    lines = []
    for s in sorted(steps, key=lambda x: x.get("position", 0)):
        block = s.get("block", {})
        text_preview = ""
        if block.get("text"):
            plain = block["text"][:80].replace("\n", " ")
            text_preview = f" | preview: {plain}"
        lines.append(
            f"step_id={s['id']} pos={s['position']} type={block.get('name', '?')}{text_preview}"
        )
    return "\n".join(lines)


@mcp.tool()
def stepik_create_text_step(lesson_id: int, text_html: str, position: int = 1) -> str:
    """
    Create a text step in a lesson. text_html is HTML content.
    Use for lesson introductions, explanations, code examples.
    """
    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "block": {
                "name": "text",
                "text": text_html,
            },
        }
    }
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    return f"Text step created: step_id={s['id']} in lesson {lesson_id} at position {position}"


@mcp.tool()
def stepik_update_text_step(step_id: int, text_html: str) -> str:
    """Update the HTML content of a text step. Only works on text-type steps."""
    existing = _get_step_source(step_id)
    block_name = existing.get("block", {}).get("name", "")
    if block_name != "text":
        return f"Error: step {step_id} is type '{block_name}', not 'text'. Use the appropriate update tool."

    body = {
        "step-source": {
            "block": {
                "name": "text",
                "text": text_html,
            }
        }
    }
    result = _api("PUT", f"step-sources/{step_id}", body)
    s = result["step-sources"][0]
    return f"Text step updated: step_id={s['id']}"


@mcp.tool()
def stepik_create_quiz_step(
    lesson_id: int,
    question: str,
    choices: list[str],
    correct_indices: list[int],
    position: int = 1,
    preserve_order: bool = False,
    feedbacks: list[str] | None = None,
    feedback_correct: str = "",
    feedback_wrong: str = "",
) -> str:
    """
    Create a multiple-choice quiz step.
    correct_indices: 0-based indices of correct answers.
    feedbacks: optional per-choice feedback strings (same length as choices).
    feedback_correct: explanation shown when the student answers correctly.
    feedback_wrong: explanation shown when the student answers incorrectly.
    """
    if feedbacks and len(feedbacks) != len(choices):
        return f"Error: feedbacks length ({len(feedbacks)}) must match choices length ({len(choices)})."

    options = []
    for i, c in enumerate(choices):
        options.append({
            "text": c,
            "is_correct": i in correct_indices,
            "feedback": feedbacks[i] if feedbacks else "",
        })

    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "block": {
                "name": "choice",
                "text": question,
                "feedback_correct": feedback_correct,
                "feedback_wrong": feedback_wrong,
                "source": {
                    "options": options,
                    "is_always_correct": False,
                    "is_html_enabled": True,
                    "preserve_order": preserve_order,
                    "is_multiple_choice": len(correct_indices) > 1,
                    "sample_size": len(choices),
                    "is_options_feedback": bool(feedbacks),
                },
            },
        }
    }
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    return f"Quiz step created: step_id={s['id']} in lesson {lesson_id}"


@mcp.tool()
def stepik_update_quiz_step(
    step_id: int,
    question: str | None = None,
    choices: list[str] | None = None,
    correct_indices: list[int] | None = None,
    preserve_order: bool | None = None,
    feedbacks: list[str] | None = None,
    feedback_correct: str | None = None,
    feedback_wrong: str | None = None,
) -> str:
    """
    Update a choice (quiz) step. Only provided fields are changed.
    If updating choices, correct_indices must also be provided.
    feedbacks: optional per-choice feedback strings (same length as choices).
    feedback_correct: explanation shown when the student answers correctly.
    feedback_wrong: explanation shown when the student answers incorrectly.
    """
    existing = _get_step_source(step_id)
    block = existing.get("block", {})
    if block.get("name") != "choice":
        return f"Error: step {step_id} is type '{block.get('name')}', not 'choice'."

    source = block.get("source", {})

    if question is not None:
        block["text"] = question

    if feedback_correct is not None:
        block["feedback_correct"] = feedback_correct

    if feedback_wrong is not None:
        block["feedback_wrong"] = feedback_wrong

    if choices is not None:
        if correct_indices is None:
            return "Error: correct_indices is required when updating choices."
        if feedbacks and len(feedbacks) != len(choices):
            return f"Error: feedbacks length ({len(feedbacks)}) must match choices length ({len(choices)})."
        options = []
        for i, c in enumerate(choices):
            options.append({
                "text": c,
                "is_correct": i in correct_indices,
                "feedback": feedbacks[i] if feedbacks else "",
            })
        source["options"] = options
        source["is_multiple_choice"] = len(correct_indices) > 1
        source["sample_size"] = len(choices)
        source["is_options_feedback"] = bool(feedbacks)

    if preserve_order is not None:
        source["preserve_order"] = preserve_order

    block["source"] = source

    body = {"step-source": {"block": block}}
    result = _api("PUT", f"step-sources/{step_id}", body)
    s = result["step-sources"][0]
    return f"Quiz step updated: step_id={s['id']}"


@mcp.tool()
def stepik_create_matching_step(
    lesson_id: int,
    question: str,
    pairs: list[dict[str, str]],
    position: int = 1,
    preserve_firsts_order: bool = False,
) -> str:
    """
    Create a matching step (connect pairs).
    pairs: list of {"first": "...", "second": "..."} dicts.
    Example: pairs=[{"first":"Python","second":"Snake"},{"first":"Java","second":"Island"}]
    """
    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "block": {
                "name": "matching",
                "text": question,
                "source": {
                    "pairs": [{"first": p["first"], "second": p["second"]} for p in pairs],
                    "preserve_firsts_order": preserve_firsts_order,
                    "is_html_enabled": True,
                },
            },
        }
    }
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    return f"Matching step created: step_id={s['id']} in lesson {lesson_id}"


@mcp.tool()
def stepik_update_matching_step(
    step_id: int,
    question: str | None = None,
    pairs: list[dict[str, str]] | None = None,
    preserve_firsts_order: bool | None = None,
) -> str:
    """
    Update a matching step. Only provided fields are changed.
    pairs: list of {"first": "...", "second": "..."} dicts.
    """
    existing = _get_step_source(step_id)
    block = existing.get("block", {})
    if block.get("name") != "matching":
        return f"Error: step {step_id} is type '{block.get('name')}', not 'matching'."

    source = block.get("source", {})

    if question is not None:
        block["text"] = question

    if pairs is not None:
        source["pairs"] = [{"first": p["first"], "second": p["second"]} for p in pairs]

    if preserve_firsts_order is not None:
        source["preserve_firsts_order"] = preserve_firsts_order

    block["source"] = source

    body = {"step-source": {"block": block}}
    result = _api("PUT", f"step-sources/{step_id}", body)
    s = result["step-sources"][0]
    return f"Matching step updated: step_id={s['id']}"


@mcp.tool()
def stepik_create_string_step(
    lesson_id: int,
    question: str,
    pattern: str,
    position: int = 1,
    use_re: bool = False,
    match_substring: bool = False,
    case_sensitive: bool = True,
) -> str:
    """
    Create a string-input step (user types a text answer).
    pattern: the correct answer (or regex if use_re=True).
    use_re: treat pattern as a regular expression.
    match_substring: accept if the pattern matches a substring of the answer.
    case_sensitive: whether matching is case-sensitive.
    """
    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "block": {
                "name": "string",
                "text": question,
                "source": {
                    "pattern": pattern,
                    "use_re": use_re,
                    "match_substring": match_substring,
                    "case_sensitive": case_sensitive,
                    "code": "",
                },
            },
        }
    }
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    return f"String step created: step_id={s['id']} in lesson {lesson_id}"


@mcp.tool()
def stepik_reorder_steps(lesson_id: int, step_ids: list[int]) -> str:
    """
    Reorder steps in a lesson. step_ids is the full list of step IDs in desired order.
    All steps of the lesson must be included.
    Example: stepik_reorder_steps(123, [55, 53, 54]) puts step 55 first, 53 second, 54 third.
    """
    result = _api("GET", "steps", params={"lesson": lesson_id})
    existing_ids = {s["id"] for s in result.get("steps", [])}

    given = set(step_ids)
    if given != existing_ids:
        missing = existing_ids - given
        extra = given - existing_ids
        parts = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if extra:
            parts.append(f"unknown: {sorted(extra)}")
        return f"Error: step_ids don't match lesson steps. {', '.join(parts)}"

    updated = []
    for pos, sid in enumerate(step_ids, start=1):
        source = _get_step_source(sid)
        body = {"step-source": {"position": pos, "block": source["block"]}}
        _api("PUT", f"step-sources/{sid}", body)
        updated.append(f"step_id={sid} → pos={pos}")

    return "Steps reordered:\n" + "\n".join(updated)


@mcp.tool()
def stepik_move_step(step_id: int, position: int) -> str:
    """Move a single step to a new position within its lesson."""
    source = _get_step_source(step_id)
    body = {"step-source": {"position": position, "block": source["block"]}}
    _api("PUT", f"step-sources/{step_id}", body)
    return f"Step {step_id} moved to position {position}."


@mcp.tool()
def stepik_delete_step(step_id: int) -> str:
    """Delete a single step by its ID."""
    _api("DELETE", f"step-sources/{step_id}")
    return f"Step {step_id} deleted."


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _upload_file(file_path: str, lesson_id: int | None = None, course_id: int | None = None) -> dict:
    """Upload a file to Stepik via multipart/form-data."""
    token = _get_token()

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_types = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp",
        "pdf": "application/pdf",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    boundary = "----StepikMCPBoundary"
    parts = []

    parts.append(
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    )

    if lesson_id is not None:
        parts.append(
            f"\r\n--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"lesson\"\r\n\r\n"
            f"{lesson_id}\r\n"
        )
    elif course_id is not None:
        parts.append(
            f"\r\n--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"course\"\r\n\r\n"
            f"{course_id}\r\n"
        )

    body = parts[0].encode() + file_data
    for p in parts[1:]:
        body += p.encode()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/attachments",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} POST attachments: {body_text}") from e


@mcp.tool()
def stepik_upload_image(
    file_path: str,
    lesson_id: int | None = None,
    course_id: int | None = None,
) -> str:
    """
    Upload an image to Stepik and get a URL for use in step HTML.
    file_path: absolute path to image file on disk.
    lesson_id or course_id: attach the image to a lesson or course (at least one recommended).
    Returns the URL to use in <img src="...">.
    """
    if not os.path.isfile(file_path):
        return f"Error: file not found: {file_path}"

    result = _upload_file(file_path, lesson_id=lesson_id, course_id=course_id)
    attachments = result.get("attachments", [])
    if not attachments:
        return "Error: upload succeeded but no attachment returned."

    a = attachments[0]
    url = f"https://stepik.org{a['file']}"
    return (
        f"Image uploaded: {a['name']} ({a['size']} bytes)\n"
        f"URL: {url}\n"
        f"Use in HTML: <img src=\"{url}\" alt=\"{a['name']}\">"
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@mcp.tool()
def stepik_health_check() -> str:
    """Verify connection and auth to Stepik API."""
    token = _get_token()
    return f"Connected to Stepik API. Token acquired (len={len(token)})."


if __name__ == "__main__":
    mcp.run()
