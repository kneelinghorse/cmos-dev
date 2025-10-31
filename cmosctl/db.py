"""
Database helper routines used by the CLI.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from cmos_core import schema
from cmos_core.migrations import migration_manager

DEFAULT_DB_PATH = Path(".cmos") / "memory.db"
MISSION_STATUSES: Sequence[str] = ("Queued", "Current", "In Progress", "Completed", "Blocked")
SESSION_ACTIONS: Sequence[str] = ("start", "complete", "blocked", "commit")


@dataclass(slots=True)
class Mission:
    id: str
    sprint_id: str | None
    name: str
    status: str
    created_at: str | None
    completed_at: str | None
    notes: str | None


@dataclass(slots=True)
class Session:
    id: int
    ts: str
    mission_id: str | None
    action: str
    agent: str | None
    summary: str | None
    details: str | None


@dataclass(slots=True)
class MissionIssue:
    mission: Mission
    field: str
    severity: str
    message: str
    kind: str


def init_database(db_path: Path | str = DEFAULT_DB_PATH, *, force: bool = False) -> Path:
    """
    Initialize the CMOS SQLite database.

    Parameters
    ----------
    db_path:
        Path to the SQLite file. Defaults to `.cmos/memory.db`.
    force:
        If true, recreate the database even if it already exists.

    Returns
    -------
    Path
        The resolved path to the initialized database file.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if force and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        schema.apply_schema(conn)
        migration_manager.apply_all(conn)
    finally:
        conn.close()

    return db_path.resolve()


def ensure_database(db_path: Path | str = DEFAULT_DB_PATH) -> Path:
    """
    Make sure a database exists at the provided path, creating it if missing.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        init_database(db_path)
    return db_path


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """
    Context manager that yields a SQLite connection with the proper row factory.
    """
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_missions(conn: sqlite3.Connection) -> list[Mission]:
    rows = conn.execute(
        """
        SELECT id, sprint_id, name, status, created_at, completed_at, notes
        FROM missions
        ORDER BY datetime(created_at) ASC, id ASC
        """
    ).fetchall()
    return [Mission(**dict(row)) for row in rows]


def _detect_mission_issues(missions: Sequence[Mission]) -> list[MissionIssue]:
    issues: list[MissionIssue] = []
    status_map: dict[str, list[Mission]] = defaultdict(list)

    for mission in missions:
        status_value = (mission.status or "").strip()
        status_map[status_value].append(mission)

        name_value = (mission.name or "").strip()
        if not name_value:
            issues.append(
                MissionIssue(
                    mission=mission,
                    field="name",
                    severity="error",
                    message="Mission name is missing.",
                    kind="missing_field",
                )
            )

        sprint_value = (mission.sprint_id or "").strip()
        if not sprint_value:
            issues.append(
                MissionIssue(
                    mission=mission,
                    field="sprint_id",
                    severity="error",
                    message="Sprint identifier is missing.",
                    kind="missing_field",
                )
            )

        if not status_value:
            issues.append(
                MissionIssue(
                    mission=mission,
                    field="status",
                    severity="error",
                    message="Mission status is missing.",
                    kind="missing_field",
                )
            )
            continue

        if status_value not in MISSION_STATUSES:
            issues.append(
                MissionIssue(
                    mission=mission,
                    field="status",
                    severity="error",
                    message=f"Mission status '{mission.status}' is invalid.",
                    kind="invalid_value",
                )
            )

        if status_value == "Completed":
            completed_value = (mission.completed_at or "").strip()
            if not completed_value:
                issues.append(
                    MissionIssue(
                        mission=mission,
                        field="completed_at",
                        severity="error",
                        message="Completed mission is missing a completed_at timestamp.",
                        kind="missing_field",
                    )
                )
        else:
            if mission.completed_at and mission.completed_at.strip():
                issues.append(
                    MissionIssue(
                        mission=mission,
                        field="completed_at",
                        severity="warning",
                        message="Non-completed mission has a completed_at timestamp.",
                        kind="inconsistent",
                    )
                )

        if status_value == "Blocked":
            notes_value = (mission.notes or "").strip()
            if not notes_value:
                issues.append(
                    MissionIssue(
                        mission=mission,
                        field="notes",
                        severity="error",
                        message="Blocked mission must include notes explaining the blocker.",
                        kind="missing_field",
                    )
                )

    for status_label in ("In Progress", "Current"):
        missions_with_status = status_map.get(status_label, [])
        if len(missions_with_status) > 1:
            for mission in missions_with_status:
                issues.append(
                    MissionIssue(
                        mission=mission,
                        field="status",
                        severity="error",
                        message=f"Multiple missions are marked '{status_label}'.",
                        kind="conflict",
                    )
                )

    return issues


def collect_mission_issues(conn: sqlite3.Connection) -> list[MissionIssue]:
    missions = list_missions(conn)
    return _detect_mission_issues(missions)


def find_incomplete_missions(
    conn: sqlite3.Connection,
) -> list[tuple[Mission, list[MissionIssue]]]:
    issues = collect_mission_issues(conn)
    grouped: dict[str, list[MissionIssue]] = defaultdict(list)

    for issue in issues:
        if issue.kind in {"missing_field", "invalid_value"}:
            grouped[issue.mission.id].append(issue)

    results: list[tuple[Mission, list[MissionIssue]]] = []
    for mission_id, items in grouped.items():
        mission = items[0].mission
        results.append((mission, items))
    return results


def get_mission(conn: sqlite3.Connection, mission_id: str) -> Mission | None:
    row = conn.execute(
        """
        SELECT id, sprint_id, name, status, created_at, completed_at, notes
        FROM missions
        WHERE id = ?
        """,
        (mission_id,),
    ).fetchone()
    return Mission(**dict(row)) if row else None


def get_current_mission(conn: sqlite3.Connection) -> Mission | None:
    row = conn.execute(
        """
        SELECT id, sprint_id, name, status, created_at, completed_at, notes
        FROM missions
        WHERE status = 'Current'
        ORDER BY datetime(created_at) ASC, id ASC
        LIMIT 1
        """
    ).fetchone()
    return Mission(**dict(row)) if row else None


def get_in_progress_mission(conn: sqlite3.Connection) -> Mission | None:
    row = conn.execute(
        """
        SELECT id, sprint_id, name, status, created_at, completed_at, notes
        FROM missions
        WHERE status = 'In Progress'
        ORDER BY datetime(created_at) ASC, id ASC
        LIMIT 1
        """
    ).fetchone()
    return Mission(**dict(row)) if row else None


def get_next_queued_mission(conn: sqlite3.Connection) -> Mission | None:
    row = conn.execute(
        """
        SELECT id, sprint_id, name, status, created_at, completed_at, notes
        FROM missions
        WHERE status = 'Queued'
        ORDER BY datetime(created_at) ASC, id ASC
        LIMIT 1
        """
    ).fetchone()
    return Mission(**dict(row)) if row else None


def add_mission(
    conn: sqlite3.Connection,
    *,
    mission_id: str,
    name: str,
    sprint_id: str,
    status: str = "Queued",
) -> None:
    if status not in MISSION_STATUSES:
        raise ValueError(f"Unsupported status '{status}'. Expected one of {', '.join(MISSION_STATUSES)}.")

    conn.execute(
        """
        INSERT INTO missions (id, sprint_id, name, status)
        VALUES (?, ?, ?, ?)
        """,
        (mission_id, sprint_id, name, status),
    )
    conn.commit()


def set_mission_status(
    conn: sqlite3.Connection,
    *,
    mission_id: str,
    status: str,
    notes: str | None = None,
    completed_at: str | None = None,
) -> None:
    if status not in MISSION_STATUSES:
        raise ValueError(f"Unsupported status '{status}'. Expected one of {', '.join(MISSION_STATUSES)}.")

    params: list[str | None] = [status, completed_at, notes, mission_id]
    conn.execute(
        """
        UPDATE missions
        SET status = ?,
            completed_at = COALESCE(?, completed_at),
            notes = COALESCE(?, notes)
        WHERE id = ?
        """,
        params,
    )
    conn.commit()


def complete_mission(
    conn: sqlite3.Connection,
    *,
    mission_id: str,
    notes: str | None = None,
    completed_at: str | None = None,
) -> Mission | None:
    mission = get_mission(conn, mission_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' not found.")

    if mission.status == "Completed":
        return None

    timestamp = completed_at or _utc_now_iso()
    conn.execute(
        """
        UPDATE missions
        SET status = 'Completed',
            completed_at = ?,
            notes = COALESCE(?, notes)
        WHERE id = ?
        """,
        (timestamp, notes, mission_id),
    )

    promoted = get_next_queued_mission(conn)
    if promoted:
        conn.execute(
            """
            UPDATE missions
            SET status = 'Current'
            WHERE id = ?
            """,
            (promoted.id,),
        )

    conn.commit()
    return promoted


def block_mission(conn: sqlite3.Connection, *, mission_id: str, reason: str) -> None:
    mission = get_mission(conn, mission_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' not found.")

    conn.execute(
        """
        UPDATE missions
        SET status = 'Blocked',
            notes = ?
        WHERE id = ?
        """,
        (reason, mission_id),
    )
    conn.commit()


def mark_in_progress(conn: sqlite3.Connection, *, mission_id: str) -> None:
    mission = get_mission(conn, mission_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' not found.")

    conn.execute(
        """
        UPDATE missions
        SET status = 'In Progress'
        WHERE id = ?
        """,
        (mission_id,),
    )
    conn.commit()


def update_mission(conn: sqlite3.Connection, *, mission_id: str, **fields: Any) -> Mission:
    mission = get_mission(conn, mission_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' not found.")

    if not fields:
        return mission

    allowed_fields = {"name", "sprint_id", "status", "notes", "completed_at"}
    updates: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed_fields:
            raise ValueError(f"Unsupported field '{key}' for mission updates.")
        if key == "status":
            if value is None:
                raise ValueError("Mission status cannot be set to null.")
            normalized = str(value).strip()
            if normalized not in MISSION_STATUSES:
                raise ValueError(f"Unsupported status '{value}'. Expected one of {', '.join(MISSION_STATUSES)}.")
            updates[key] = normalized
        else:
            updates[key] = value

    if not updates:
        return mission

    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values())
    params.append(mission_id)

    conn.execute(
        f"""
        UPDATE missions
        SET {assignments}
        WHERE id = ?
        """,
        params,
    )
    conn.commit()
    return get_mission(conn, mission_id)


def utc_now_iso() -> str:
    """
    Exported helper for other modules that need an ISO8601 UTC timestamp.
    """
    return _utc_now_iso()


def _normalize_session_action(action: str) -> str:
    normalized = action.strip().lower()
    if normalized not in SESSION_ACTIONS:
        expected = ", ".join(SESSION_ACTIONS)
        raise ValueError(f"Unsupported session action '{action}'. Expected one of {expected}.")
    return normalized


def _status_to_action(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().lower()
    mapping = {
        "in_progress": "start",
        "started": "start",
        "start": "start",
        "complete": "complete",
        "completed": "complete",
        "done": "complete",
        "blocked": "blocked",
        "commit": "commit",
        "committed": "commit",
        "commit_logged": "commit",
    }
    return mapping.get(normalized, normalized if normalized in SESSION_ACTIONS else None)


def log_session(
    conn: sqlite3.Connection,
    *,
    action: str,
    mission_id: str | None = None,
    agent: str | None = None,
    summary: str | None = None,
    details: str | None = None,
    ts: str | None = None,
) -> int:
    normalized_action = _normalize_session_action(action)
    timestamp = ts or _utc_now_iso()
    mission_value = mission_id.strip() if isinstance(mission_id, str) and mission_id.strip() else None
    agent_value = agent.strip() if isinstance(agent, str) and agent.strip() else None
    summary_value = summary.strip() if isinstance(summary, str) and summary.strip() else None
    details_value = details.strip() if isinstance(details, str) and details.strip() else None

    cursor = conn.execute(
        """
        INSERT INTO sessions (ts, mission_id, action, agent, summary, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (timestamp, mission_value, normalized_action, agent_value, summary_value, details_value),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_sessions(conn: sqlite3.Connection, *, mission_id: str | None = None) -> list[Session]:
    params: list[str] = []
    query = """
        SELECT id, ts, mission_id, action, agent, summary, details
        FROM sessions
    """
    if mission_id:
        query += " WHERE mission_id = ?"
        params.append(mission_id)
    query += " ORDER BY datetime(ts) DESC, id DESC"

    rows = conn.execute(query, params).fetchall()
    return [Session(**dict(row)) for row in rows]


def get_session(conn: sqlite3.Connection, session_id: int) -> Session | None:
    row = conn.execute(
        """
        SELECT id, ts, mission_id, action, agent, summary, details
        FROM sessions
        WHERE id = ?
        """,
        (session_id,),
    ).fetchone()
    return Session(**dict(row)) if row else None


def replace_missions(
    conn: sqlite3.Connection,
    missions: Sequence[dict[str, str | None]],
) -> None:
    """
    Replace all mission rows with the provided collection.
    """
    conn.execute("DELETE FROM missions")
    conn.executemany(
        """
        INSERT INTO missions (id, sprint_id, name, status, completed_at, notes)
        VALUES (:id, :sprint_id, :name, :status, :completed_at, :notes)
        """,
        missions,
    )
    conn.commit()


def replace_sessions(
    conn: sqlite3.Connection,
    sessions: Sequence[dict[str, Any]],
) -> None:
    """
    Replace all session rows with the provided collection.
    """
    normalized_rows: list[dict[str, Any]] = []
    for index, session in enumerate(sessions, start=1):
        if not isinstance(session, dict):
            raise ValueError(f"Session entry #{index} is not a JSON object.")

        ts_raw = session.get("ts")
        if ts_raw is None:
            raise ValueError(f"Session entry #{index} is missing 'ts'.")
        ts_value = str(ts_raw).strip()
        if not ts_value:
            raise ValueError(f"Session entry #{index} has an empty 'ts' value.")

        action_raw = session.get("action") or _status_to_action(session.get("status"))
        if not action_raw:
            raise ValueError(f"Session entry #{index} is missing 'action'.")
        action_value = _normalize_session_action(str(action_raw))

        mission_raw = session.get("mission_id") or session.get("mission")
        if mission_raw is None:
            mission_value = None
        elif isinstance(mission_raw, str):
            mission_value = mission_raw.strip() or None
        else:
            mission_value = str(mission_raw).strip() or None

        agent_raw = session.get("agent")
        if agent_raw is None:
            agent_value = None
        elif isinstance(agent_raw, str):
            agent_value = agent_raw.strip() or None
        else:
            agent_value = str(agent_raw).strip() or None

        summary_raw = session.get("summary")
        if summary_raw is None:
            summary_value = None
        elif isinstance(summary_raw, str):
            summary_value = summary_raw.strip() or None
        else:
            summary_value = str(summary_raw).strip() or None

        details_raw = session.get("details")
        extras = {
            key: value
            for key, value in session.items()
            if key
            not in {"ts", "mission", "mission_id", "action", "status", "agent", "summary", "details"}
        }

        if details_raw is None and extras:
            details_candidate: Any = extras
        elif details_raw is not None and extras:
            if isinstance(details_raw, dict):
                details_candidate = {**details_raw, **extras}
            else:
                details_candidate = {"details": details_raw, **extras}
        else:
            details_candidate = details_raw

        if isinstance(details_candidate, (dict, list)):
            details_value = json.dumps(details_candidate, ensure_ascii=False)
        elif details_candidate is None:
            details_value = None
        else:
            details_value = str(details_candidate).strip() or None

        normalized_rows.append(
            {
                "ts": ts_value,
                "mission_id": mission_value,
                "action": action_value,
                "agent": agent_value,
                "summary": summary_value,
                "details": details_value,
            }
        )

    conn.execute("DELETE FROM sessions")
    if normalized_rows:
        conn.executemany(
            """
            INSERT INTO sessions (ts, mission_id, action, agent, summary, details)
            VALUES (:ts, :mission_id, :action, :agent, :summary, :details)
            """,
            normalized_rows,
        )
    conn.commit()
