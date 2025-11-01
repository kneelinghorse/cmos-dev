from __future__ import annotations

import getpass
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

import yaml

from . import db as db_commands
from .recall import RecallResult, recall_knowledge

DEFAULT_DB_PATH = db_commands.DEFAULT_DB_PATH
DEFAULT_BACKLOG_PATH = Path("cmos/missions/backlog.yaml")
DEFAULT_SESSIONS_PATH = Path("cmos/SESSIONS.jsonl")
DEFAULT_PROJECT_CONTEXT_PATH = Path("cmos/PROJECT_CONTEXT.json")
DEFAULT_MASTER_CONTEXT_PATH = Path("cmos/context/MASTER_CONTEXT.json")

SESSION_STATUS_FROM_ACTION = {
    "start": "in_progress",
    "complete": "completed",
    "blocked": "blocked",
    "commit": "commit",
}


@dataclass(slots=True)
class MissionContext:
    mission: db_commands.Mission
    db_path: Path
    backlog_path: Path
    sessions_path: Path
    project_context_path: Path
    master_context_path: Path


@dataclass(slots=True)
class MissionRunOutcome:
    summary: str
    notes: str
    next_hint: str | None = None
    details: dict[str, Any] | None = None
    completed_at: str | None = None


@dataclass(slots=True)
class TriggerResult:
    trigger: str
    success: bool
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


TriggerHandler = Callable[..., TriggerResult]


def _default_agent() -> str:
    env_agent = os.getenv("CMOS_AGENT")
    if env_agent and env_agent.strip():
        return env_agent.strip()
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - fallback for unusual environments
        return "unknown"


def _normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


def _extract_header(text: str) -> str:
    header_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            header_lines.append(line)
        else:
            break
    return "\n".join(header_lines)


def _derive_sprint_status(original_status: str | None, mission_statuses: Iterable[str | None]) -> str:
    statuses = {status for status in mission_statuses if status}
    if not statuses:
        return original_status or "Queued"
    if statuses == {"Completed"}:
        return "Completed"
    if "Blocked" in statuses:
        return "Blocked"
    if "In Progress" in statuses:
        return "In Progress"
    if "Current" in statuses:
        return "Current"
    if statuses == {"Queued"}:
        if original_status and original_status.lower() == "planned":
            return original_status
        return "Queued"
    if statuses == {"Completed", "Queued"}:
        return "In Progress"
    return original_status or "In Progress"


def _parse_details_field(details: str | None) -> Any:
    if details is None:
        return None
    text = details.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _load_backlog_documents(backlog_path: Path) -> tuple[str, list[Any]]:
    if not backlog_path.exists():
        raise FileNotFoundError(f"Backlog file not found at {backlog_path}")
    raw_text = backlog_path.read_text(encoding="utf-8")
    header = _extract_header(raw_text)
    docs = list(yaml.safe_load_all(raw_text))
    if not docs:
        docs.append({})
    if len(docs) < 2:
        docs.append({})
    return header, docs


def _sync_backlog(db_path: Path, backlog_path: Path) -> None:
    header, docs = _load_backlog_documents(backlog_path)
    with db_commands.connect(db_path) as conn:
        missions = db_commands.list_missions(conn)
    mission_map: Dict[str, db_commands.Mission] = {mission.id: mission for mission in missions}

    second_doc = docs[1]
    if not isinstance(second_doc, dict):
        second_doc = {}
        docs[1] = second_doc

    domain_fields = second_doc.setdefault("domainFields", {})
    if not isinstance(domain_fields, dict):
        domain_fields = {}
        second_doc["domainFields"] = domain_fields

    sprints = domain_fields.setdefault("sprints", [])
    if not isinstance(sprints, list):
        sprints = []
        domain_fields["sprints"] = sprints

    sprint_map: Dict[str | None, dict[str, Any]] = {}
    for sprint in sprints:
        if isinstance(sprint, dict):
            sprint_id = sprint.get("sprintId")
            if sprint_id not in sprint_map:
                sprint_map[sprint_id] = sprint

    def ensure_sprint(mission: db_commands.Mission) -> dict[str, Any]:
        sprint_id = mission.sprint_id or "Unassigned"
        sprint = sprint_map.get(sprint_id)
        if sprint is None:
            sprint = {
                "sprintId": sprint_id,
                "title": mission.sprint_id or sprint_id,
                "focus": "",
                "status": "Queued",
                "missions": [],
            }
            sprints.append(sprint)
            sprint_map[sprint_id] = sprint
        missions_list = sprint.setdefault("missions", [])
        if not isinstance(missions_list, list):
            missions_list = []
            sprint["missions"] = missions_list
        return sprint

    for mission in missions:
        sprint = ensure_sprint(mission)
        missions_list = sprint["missions"]
        entry = None
        for item in missions_list:
            if isinstance(item, dict) and item.get("id") == mission.id:
                entry = item
                break
        if entry is None:
            entry = {"id": mission.id, "name": mission.name}
            missions_list.append(entry)
        entry["name"] = mission.name
        entry["status"] = mission.status
        if mission.completed_at:
            entry["completed_at"] = mission.completed_at
        else:
            entry.pop("completed_at", None)
        if mission.notes:
            entry["notes"] = mission.notes
        else:
            entry.pop("notes", None)

    for sprint in sprints:
        if not isinstance(sprint, dict):
            continue
        missions_list = sprint.get("missions") or []
        statuses = [item.get("status") for item in missions_list if isinstance(item, dict)]
        sprint["status"] = _derive_sprint_status(sprint.get("status"), statuses)

    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    with backlog_path.open("w", encoding="utf-8") as handle:
        if header:
            handle.write(header.rstrip() + "\n")
        yaml.safe_dump_all(docs, handle, sort_keys=False)


def _sync_sessions(db_path: Path, sessions_path: Path) -> None:
    with db_commands.connect(db_path) as conn:
        sessions = db_commands.list_sessions(conn)

    sessions_sorted = sorted(sessions, key=lambda entry: (entry.ts, entry.id))
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    with sessions_path.open("w", encoding="utf-8") as handle:
        for session in sessions_sorted:
            record = {
                "ts": session.ts,
                "mission": session.mission_id,
                "action": session.action,
                "status": SESSION_STATUS_FROM_ACTION.get(session.action, session.action),
                "agent": session.agent,
                "summary": session.summary,
            }
            details = _parse_details_field(session.details)
            if details is not None:
                record["details"] = details
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")


def _update_project_context(project_context_path: Path, *, mission_id: str, completion_ts: str) -> None:
    if not project_context_path.exists():
        raise FileNotFoundError(f"Project context file not found at {project_context_path}")

    with project_context_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    working = data.setdefault("working_memory", {})
    session_count = working.get("session_count", 0)
    try:
        count_int = int(session_count)
    except (TypeError, ValueError):
        count_int = 0
    working["session_count"] = count_int + 1
    working["last_session"] = completion_ts
    working["last_mission"] = mission_id

    project_context_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_master_context(master_context_path: Path) -> dict[str, Any]:
    if not master_context_path.exists():
        raise FileNotFoundError(f"Master context file not found at {master_context_path}")
    with master_context_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _format_check_in_summary(
    project_context: dict[str, Any],
    master_context: dict[str, Any],
    *,
    mission: db_commands.Mission | None,
    next_mission: db_commands.Mission | None,
) -> dict[str, Any]:
    working = project_context.get("working_memory", {})
    session_count = working.get("session_count", 0)
    last_session = working.get("last_session")
    project = project_context.get("project", {})
    project_name = project.get("name", "CMOS")
    current_sprint = project.get("status") or working.get("active_domain")

    decisions = master_context.get("key_decisions_log", [])
    recent_decisions = [
        {"date": item.get("date"), "decision": item.get("decision"), "impact": item.get("impact")}
        for item in decisions[-3:]
        if isinstance(item, dict)
    ]

    summary_lines = [
        f"Project: {project_name}",
        f"Sessions: {session_count} (last at {last_session})" if last_session else f"Sessions: {session_count}",
    ]
    if current_sprint:
        summary_lines.append(f"Status: {current_sprint}")
    if mission:
        summary_lines.append(f"In Progress: {mission.id} – {mission.name}")
    if next_mission:
        summary_lines.append(f"Next Up: {next_mission.id} – {next_mission.name}")

    return {
        "summary": "\n".join(summary_lines),
        "recent_decisions": recent_decisions,
        "last_session": last_session,
    }


class TriggerRegistry:
    def __init__(
        self,
        *,
        db_path: Path = DEFAULT_DB_PATH,
        backlog_path: Path = DEFAULT_BACKLOG_PATH,
        sessions_path: Path = DEFAULT_SESSIONS_PATH,
        project_context_path: Path = DEFAULT_PROJECT_CONTEXT_PATH,
        master_context_path: Path = DEFAULT_MASTER_CONTEXT_PATH,
        agent: str | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.backlog_path = Path(backlog_path)
        self.sessions_path = Path(sessions_path)
        self.project_context_path = Path(project_context_path)
        self.master_context_path = Path(master_context_path)
        self.agent = agent or _default_agent()
        self._handlers: dict[str, TriggerHandler] = {}
        self._trigger_meta: dict[str, dict[str, Any]] = {}

    def register(
        self,
        phrase: str,
        handler: TriggerHandler,
        *,
        description: str | None = None,
        aliases: Iterable[str] | None = None,
    ) -> None:
        base_norm = _normalize_phrase(phrase)
        meta = self._trigger_meta.setdefault(
            base_norm,
            {"phrase": phrase, "description": description, "aliases": set()},
        )
        if description:
            meta["description"] = description
        self._handlers[base_norm] = handler
        if aliases:
            alias_set: set[str] = meta.setdefault("aliases", set())
            for alias in aliases:
                alias_norm = _normalize_phrase(alias)
                self._handlers[alias_norm] = handler
                alias_set.add(alias)

    def handle(self, phrase: str, **kwargs: Any) -> TriggerResult:
        normalized = _normalize_phrase(phrase)
        handler = self._handlers.get(normalized)
        if handler is None:
            raise KeyError(f"No trigger registered for phrase '{phrase}'.")
        return handler(self, phrase=phrase, **kwargs)

    def available_triggers(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for meta in self._trigger_meta.values():
            aliases = sorted(meta.get("aliases", []))
            results.append(
                {
                    "phrase": meta["phrase"],
                    "description": meta.get("description"),
                    "aliases": aliases,
                }
            )
        return sorted(results, key=lambda item: item["phrase"].lower())

    def recall_knowledge(self, query: str, *, limit: int = 5) -> List[RecallResult]:
        """Proxy helper that keeps recall paths aligned with the registry config."""

        kb_root = self.project_context_path.parent
        return list(recall_knowledge(query, limit=limit, kb_root=kb_root))

    def _select_active_mission(self) -> tuple[db_commands.Mission | None, bool]:
        with db_commands.connect(self.db_path) as conn:
            mission = db_commands.get_in_progress_mission(conn)
            if mission:
                return mission, False
            mission = db_commands.get_current_mission(conn)
            if mission:
                db_commands.mark_in_progress(conn, mission_id=mission.id)
                return db_commands.get_mission(conn, mission.id), True
            mission = db_commands.get_next_queued_mission(conn)
            if mission:
                db_commands.mark_in_progress(conn, mission_id=mission.id)
                return db_commands.get_mission(conn, mission.id), True
            return None, False

    def _run_current_mission(
        self,
        *,
        phrase: str,
        executor: Callable[[MissionContext], MissionRunOutcome],
        start_summary: str | None = None,
    ) -> TriggerResult:
        mission, status_changed = self._select_active_mission()
        if mission is None:
            return TriggerResult(
                trigger=phrase,
                success=False,
                message="No mission found with status In Progress, Current, or Queued.",
            )

        start_ts: str | None = None
        if status_changed:
            start_ts = db_commands.utc_now_iso()
            with db_commands.connect(self.db_path) as conn:
                db_commands.log_session(
                    conn,
                    action="start",
                    mission_id=mission.id,
                    agent=self.agent,
                    summary=start_summary or f"Starting {mission.name}",
                    ts=start_ts,
                )
            _sync_backlog(self.db_path, self.backlog_path)

        context = MissionContext(
            mission=mission,
            db_path=self.db_path,
            backlog_path=self.backlog_path,
            sessions_path=self.sessions_path,
            project_context_path=self.project_context_path,
            master_context_path=self.master_context_path,
        )

        outcome = executor(context)
        completion_ts = outcome.completed_at or db_commands.utc_now_iso()

        details = outcome.details.copy() if outcome.details else {}
        if outcome.next_hint:
            details.setdefault("next_hint", outcome.next_hint)
        details_payload = json.dumps(details) if details else None

        with db_commands.connect(self.db_path) as conn:
            promoted = db_commands.complete_mission(
                conn,
                mission_id=mission.id,
                notes=outcome.notes,
                completed_at=completion_ts,
            )
            db_commands.log_session(
                conn,
                action="complete",
                mission_id=mission.id,
                agent=self.agent,
                summary=outcome.summary,
                details=details_payload,
                ts=completion_ts,
            )

        _sync_backlog(self.db_path, self.backlog_path)
        _sync_sessions(self.db_path, self.sessions_path)
        _update_project_context(self.project_context_path, mission_id=mission.id, completion_ts=completion_ts)

        payload: dict[str, Any] = {
            "mission_id": mission.id,
            "completed_at": completion_ts,
            "next_mission": promoted.id if promoted else None,
        }
        if outcome.next_hint:
            payload["next_hint"] = outcome.next_hint

        return TriggerResult(
            trigger=phrase,
            success=True,
            message=f"Mission {mission.id} completed.",
            payload=payload,
        )

    def _handle_check_in(self, *, phrase: str) -> TriggerResult:
        project_context = {}
        master_context = {}
        try:
            with self.project_context_path.open("r", encoding="utf-8") as handle:
                project_context = json.load(handle)
        except FileNotFoundError:
            project_context = {}
        try:
            master_context = _read_master_context(self.master_context_path)
        except FileNotFoundError:
            master_context = {}

        with db_commands.connect(self.db_path) as conn:
            mission = db_commands.get_in_progress_mission(conn)
            next_mission = db_commands.get_next_queued_mission(conn)

        payload = _format_check_in_summary(
            project_context,
            master_context,
            mission=mission,
            next_mission=next_mission,
        )
        return TriggerResult(
            trigger=phrase,
            success=True,
            message="Check-in summary generated.",
            payload=payload,
        )

    def register_default_triggers(self) -> None:
        self.register(
            "run current mission",
            lambda registry, **kwargs: registry._run_current_mission(**kwargs),
            description="Execute the active mission workflow (status transition, session logging, completion).",
            aliases=["run the current mission", "run mission now"],
        )
        self.register(
            "let's check-in",
            lambda registry, **kwargs: registry._handle_check_in(**kwargs),
            description="Summarize recent activity from project and master context files.",
            aliases=["lets check in", "status check"],
        )


def default_registry(**kwargs: Any) -> TriggerRegistry:
    registry = TriggerRegistry(**kwargs)
    registry.register_default_triggers()
    return registry
