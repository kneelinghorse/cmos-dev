from __future__ import annotations

import getpass
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import typer
import yaml

from . import db as db_commands

app = typer.Typer(help="CMOS command-line interface", add_completion=False, no_args_is_help=True)
mission_app = typer.Typer(help="Mission management commands", add_completion=False)
db_app = typer.Typer(help="Database maintenance commands", add_completion=False)
session_app = typer.Typer(help="Session logging commands", add_completion=False)
hook_app = typer.Typer(help="Git hook utilities", add_completion=False)
export_app = typer.Typer(help="Export data to human-readable files", add_completion=False)

app.add_typer(db_app, name="db")
app.add_typer(mission_app, name="mission")
app.add_typer(session_app, name="session")
app.add_typer(hook_app, name="hook")
app.add_typer(export_app, name="export")

STATUS_NORMALIZATION = {
    "Queued": "Queued",
    "queued": "Queued",
    "Current": "Current",
    "current": "Current",
    "In Progress": "In Progress",
    "in progress": "In Progress",
    "In_Progress": "In Progress",
    "in_progress": "In Progress",
    "inprogress": "In Progress",
    "Completed": "Completed",
    "completed": "Completed",
    "Blocked": "Blocked",
    "blocked": "Blocked",
    "Planned": "Queued",
    "planned": "Queued",
}

SESSION_STATUS_FROM_ACTION = {
    "start": "in_progress",
    "complete": "completed",
    "blocked": "blocked",
    "commit": "commit",
}

DEFAULT_BACKLOG_PATH = Path("cmos/missions/backlog.yaml")
DEFAULT_SESSIONS_PATH = Path("cmos/SESSIONS.jsonl")
DEFAULT_PROJECT_CONTEXT_PATH = Path("cmos/PROJECT_CONTEXT.json")


@dataclass(slots=True)
class BacklogTemplate:
    header: str
    docs: list[dict[str, Any]]
    sprint_order: list[str]
    sprint_map: dict[str, dict[str, Any]]


def _ensure_context(ctx: typer.Context) -> Path:
    if ctx.obj is None or "db_path" not in ctx.obj:
        raise typer.Exit(code=1)
    return Path(ctx.obj["db_path"])


def _format_table(rows: Iterable[db_commands.Mission]) -> list[str]:
    header = f"{'ID':<8} {'Sprint':<12} {'Status':<12} {'Name'}"
    separator = "-" * len(header)
    lines = [header, separator]
    for mission in rows:
        sprint = mission.sprint_id or "-"
        lines.append(f"{mission.id:<8} {sprint:<12} {mission.status:<12} {mission.name}")
    return lines


_SESSION_ACTIONS = set(db_commands.SESSION_ACTIONS)
_SESSION_ACTIONS_DISPLAY = ", ".join(db_commands.SESSION_ACTIONS)


def _default_agent() -> str:
    env_agent = os.getenv("CMOS_AGENT")
    if env_agent and env_agent.strip():
        return env_agent.strip()
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - fallback for unusual environments
        return "unknown"


def _validate_session_action(action: str) -> str:
    normalized = action.strip().lower()
    if normalized not in _SESSION_ACTIONS:
        raise typer.BadParameter(f"Action must be one of {_SESSION_ACTIONS_DISPLAY}.")
    return normalized


def _format_sessions_table(rows: Iterable[db_commands.Session]) -> list[str]:
    header = f"{'ID':<6} {'Timestamp':<20} {'Mission':<10} {'Action':<8} {'Agent':<12} {'Summary'}"
    separator = "-" * len(header)
    lines = [header, separator]
    for session in rows:
        mission = session.mission_id or "-"
        agent = session.agent or "-"
        summary = session.summary or "-"
        if len(summary) > 60:
            summary = summary[:57] + "..."
        lines.append(
            f"{session.id:<6} {session.ts:<20} {mission:<10} {session.action:<8} {agent:<12} {summary}"
        )
    return lines


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text else None


def _normalize_status_input(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise typer.BadParameter("Status cannot be empty.")

    direct = STATUS_NORMALIZATION.get(normalized)
    if direct:
        return direct

    title_candidate = normalized.title()
    direct = STATUS_NORMALIZATION.get(title_candidate)
    if direct:
        return direct

    simplified = normalized.replace("_", " ").strip()
    direct = STATUS_NORMALIZATION.get(simplified)
    if direct:
        return direct

    simplified_key = simplified.lower().replace(" ", "")
    for key, canonical in STATUS_NORMALIZATION.items():
        key_normalized = key.lower().replace(" ", "").replace("_", "")
        if key_normalized == simplified_key:
            return canonical

    for status in db_commands.MISSION_STATUSES:
        match_key = status.lower().replace(" ", "")
        if match_key == simplified_key:
            return status

    expected = ", ".join(db_commands.MISSION_STATUSES)
    raise typer.BadParameter(f"Unsupported status '{value}'. Expected one of {expected}.")


@app.callback()
def cli(
    ctx: typer.Context,
    db_path: Path = typer.Option(
        db_commands.DEFAULT_DB_PATH,
        "--db-path",
        help="Path to the CMOS SQLite database (default: .cmos/memory.db)",
    ),
) -> None:
    ctx.obj = {"db_path": Path(db_path)}
    db_commands.ensure_database(db_path)


@db_app.command("init")
def db_init(
    path: Path = typer.Option(
        db_commands.DEFAULT_DB_PATH,
        "--path",
        help="SQLite database path (default: .cmos/memory.db)",
    ),
    force: bool = typer.Option(False, "--force", help="Recreate the database if it already exists"),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress success output"),
) -> None:
    db_path = Path(path)
    existed_before = db_path.exists()
    final_path = db_commands.init_database(db_path, force=force)

    if quiet:
        return

    if existed_before and not force:
        typer.echo(f"Ensured schema at {final_path}")
    elif existed_before and force:
        typer.echo(f"Recreated database at {final_path}")
    else:
        typer.echo(f"Created database at {final_path}")


@db_app.command("shell")
def db_shell(
    ctx: typer.Context,
    command: str | None = typer.Option(
        None,
        "--command",
        "-c",
        help="Optional SQLite command to execute before exiting the shell",
    ),
    sqlite_bin: str = typer.Option(
        "sqlite3",
        "--sqlite-bin",
        help="SQLite executable to use (default: sqlite3)",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    executable = sqlite_bin or "sqlite3"
    resolved = shutil.which(executable)
    if resolved is None:
        typer.echo(f"Unable to locate SQLite executable '{executable}'.")
        raise typer.Exit(code=1)

    args = [resolved, str(db_path)]
    if command:
        args.append(command)

    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


@mission_app.command("list")
def mission_list(ctx: typer.Context) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        missions = db_commands.list_missions(conn)

    if not missions:
        typer.echo("No missions found. Use 'cmosctl mission add' to create one.")
        raise typer.Exit(code=0)

    for line in _format_table(missions):
        typer.echo(line)


@mission_app.command("show")
def mission_show(
    ctx: typer.Context,
    mission_id: str = typer.Argument(..., help="Mission identifier to display"),
) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        mission = db_commands.get_mission(conn, mission_id=mission_id)

    if mission is None:
        typer.echo(f"Mission {mission_id} not found.")
        raise typer.Exit(code=1)

    typer.echo(f"ID: {mission.id}")
    typer.echo(f"Name: {mission.name}")
    typer.echo(f"Sprint: {mission.sprint_id or '-'}")
    typer.echo(f"Status: {mission.status}")
    typer.echo(f"Created: {mission.created_at or '-'}")
    typer.echo(f"Completed: {mission.completed_at or '-'}")
    typer.echo("Notes:")
    typer.echo((mission.notes or "-").strip() or "-")


@mission_app.command("edit")
def mission_edit(
    ctx: typer.Context,
    mission_id: str = typer.Argument(..., help="Mission identifier to edit"),
    name: str | None = typer.Option(None, "--name", "-n", help="Update the mission name"),
    status: str | None = typer.Option(None, "--status", "-s", help="Update the mission status"),
    sprint: str | None = typer.Option(None, "--sprint", "-p", help="Update the sprint identifier"),
    notes: str | None = typer.Option(None, "--notes", help="Update or clear mission notes"),
    completed_at: str | None = typer.Option(
        None,
        "--completed-at",
        help="Update or clear the completed_at timestamp (ISO 8601 format preferred)",
    ),
    editor: bool | None = typer.Option(
        None,
        "--editor/--no-editor",
        help="Open the mission in $EDITOR for manual editing (default: editor if no flags provided)",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        mission = db_commands.get_mission(conn, mission_id=mission_id)
        if mission is None:
            typer.echo(f"Mission {mission_id} not found.")
            raise typer.Exit(code=1)

        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = name.strip()
        if sprint is not None:
            updates["sprint_id"] = _optional_str(sprint)
        if status is not None:
            updates["status"] = _normalize_status_input(status)
        if notes is not None:
            updates["notes"] = _optional_str(notes)
        if completed_at is not None:
            updates["completed_at"] = _optional_str(completed_at)

        use_editor = editor if editor is not None else (not updates)

        if use_editor:
            payload = {
                "id": mission.id,
                "sprint_id": mission.sprint_id,
                "name": mission.name,
                "status": mission.status,
                "completed_at": mission.completed_at,
                "notes": mission.notes,
            }
            initial_text = yaml.safe_dump(payload, sort_keys=False)
            edited = typer.edit(initial_text, extension=".yaml")
            if edited is None:
                typer.echo("Edit cancelled; no changes applied.")
                raise typer.Exit(code=0)
            try:
                updated_payload = yaml.safe_load(edited) or {}
            except yaml.YAMLError as exc:
                typer.echo(f"Failed to parse edited mission: {exc}")
                raise typer.Exit(code=1) from exc

            if not isinstance(updated_payload, dict):
                typer.echo("Edited content must be a mapping.")
                raise typer.Exit(code=1)

            for field_name in ("name", "sprint_id", "status", "completed_at", "notes"):
                if field_name not in updated_payload:
                    continue
                value = updated_payload[field_name]
                if field_name == "status" and value is not None:
                    updates["status"] = _normalize_status_input(str(value))
                elif field_name == "sprint_id":
                    updates["sprint_id"] = _optional_str(str(value) if value is not None else None)
                elif field_name == "completed_at":
                    updates["completed_at"] = _optional_str(str(value) if value is not None else None)
                elif field_name == "notes":
                    updates["notes"] = _optional_str(str(value) if value is not None else None)
                elif field_name == "name":
                    updates["name"] = str(value).strip() if value is not None else ""

        if not updates:
            typer.echo("No changes detected.")
            raise typer.Exit(code=0)

        try:
            updated = db_commands.update_mission(conn, mission_id=mission.id, **updates)
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc

    typer.echo(f"Mission {updated.id} updated.")


@mission_app.command("verify")
def mission_verify(ctx: typer.Context) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        issues = db_commands.collect_mission_issues(conn)

    if not issues:
        typer.echo("All missions verified.")
        raise typer.Exit(code=0)

    error_count = 0
    for issue in issues:
        prefix = issue.severity.upper()
        typer.echo(f"[{prefix}] {issue.mission.id} ({issue.field}) - {issue.message}")
        if issue.severity.lower() == "error":
            error_count += 1

    if error_count:
        raise typer.Exit(code=1)


@mission_app.command("incomplete")
def mission_incomplete(ctx: typer.Context) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        results = db_commands.find_incomplete_missions(conn)

    if not results:
        typer.echo("No incomplete missions found.")
        return

    for mission, issues in results:
        typer.echo(f"{mission.id} [{mission.status}] - {mission.name}")
        for issue in issues:
            typer.echo(f"  - ({issue.field}) {issue.message}")


@mission_app.command("audit")
def mission_audit(
    ctx: typer.Context,
    sprint: str | None = typer.Argument(
        None, help="Sprint identifier to audit (default: all sprints)"
    ),
) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        missions = db_commands.list_missions(conn)
        issues = db_commands.collect_mission_issues(conn)

    if not missions:
        typer.echo("No missions found.")
        raise typer.Exit(code=0)

    sprint_map: dict[str, list[db_commands.Mission]] = {}
    sprint_order: list[str] = []
    for mission in missions:
        key = mission.sprint_id or "Unassigned"
        if key not in sprint_map:
            sprint_map[key] = []
            sprint_order.append(key)
        sprint_map[key].append(mission)

    if sprint:
        if sprint not in sprint_map:
            typer.echo(f"Sprint '{sprint}' not found.")
            raise typer.Exit(code=1)
        sprint_sequence = [sprint]
    else:
        sprint_sequence = sprint_order

    issues_by_sprint: dict[str, list[db_commands.MissionIssue]] = defaultdict(list)
    for issue in issues:
        key = issue.mission.sprint_id or "Unassigned"
        issues_by_sprint[key].append(issue)

    for index, sprint_id in enumerate(sprint_sequence):
        if index:
            typer.echo("")

        missions_in_sprint = sprint_map[sprint_id]
        typer.echo(f"Sprint: {sprint_id} ({len(missions_in_sprint)} missions)")

        status_counts = Counter(m.status for m in missions_in_sprint)
        counts_line = ", ".join(
            f"{status}: {status_counts.get(status, 0)}" for status in db_commands.MISSION_STATUSES
        )
        typer.echo(f"  Statuses: {counts_line}")

        active = next((m for m in missions_in_sprint if m.status == "In Progress"), None)
        if active is None:
            active = next((m for m in missions_in_sprint if m.status == "Current"), None)
        if active:
            typer.echo(f"  Active: {active.id} [{active.status}] - {active.name}")
        else:
            typer.echo("  Active: None")

        next_queued = next((m for m in missions_in_sprint if m.status == "Queued"), None)
        if next_queued:
            typer.echo(f"  Next queued: {next_queued.id} - {next_queued.name}")
        else:
            typer.echo("  Next queued: None")

        sprint_issues = issues_by_sprint.get(sprint_id, [])
        if sprint_issues:
            typer.echo("  Issues:")
            for issue in sprint_issues:
                typer.echo(f"    - {issue.mission.id} ({issue.field}): {issue.message}")
        else:
            typer.echo("  Issues: none")


@mission_app.command("next")
def mission_next(
    ctx: typer.Context,
    start: bool = typer.Option(
        False,
        "--start",
        help="Mark the current mission as In Progress after displaying it.",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        mission = db_commands.get_in_progress_mission(conn) or db_commands.get_current_mission(conn)

        if mission is None:
            typer.echo("No mission with status Current or In Progress found.")
            raise typer.Exit(code=1)

        typer.echo(f"{mission.id} [{mission.status}] - {mission.name}")

        if start and mission.status == "Current":
            db_commands.mark_in_progress(conn, mission_id=mission.id)
            typer.echo(f"Mission {mission.id} marked as In Progress.")


@mission_app.command("complete")
def mission_complete(
    ctx: typer.Context,
    mission_id: str = typer.Argument(..., help="Mission identifier to mark as completed"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Optional completion notes"),
) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        try:
            promoted = db_commands.complete_mission(conn, mission_id=mission_id, notes=notes)
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc

    typer.echo(f"Mission {mission_id} marked as Completed.")
    if promoted:
        typer.echo(f"Mission {promoted.id} promoted to Current.")


@mission_app.command("block")
def mission_block(
    ctx: typer.Context,
    mission_id: str = typer.Argument(..., help="Mission identifier to block"),
    reason: str | None = typer.Option(
        None,
        "--reason",
        "-r",
        help="Reason for blocking the mission",
        prompt="Reason for blocking the mission",
    ),
) -> None:
    assert reason is not None  # appeases type checkers; prompt ensures non-None
    reason = reason.strip()
    if not reason:
        typer.echo("Blocking reason cannot be empty.")
        raise typer.Exit(code=1)

    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        try:
            db_commands.block_mission(conn, mission_id=mission_id, reason=reason)
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc

    typer.echo(f"Mission {mission_id} marked as Blocked.")


@mission_app.command("add")
def mission_add(
    ctx: typer.Context,
    mission_id: str = typer.Argument(..., help="Mission identifier to add"),
    name: str = typer.Argument(..., help="Human readable mission name"),
    sprint_id: str = typer.Argument(..., help="Sprint identifier (e.g. Sprint 1)"),
    status: str = typer.Option(
        "Queued",
        "--status",
        "-s",
        help="Initial mission status (default: Queued)",
    ),
) -> None:
    normalized_status = _normalize_status_input(status)

    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        try:
            db_commands.add_mission(
                conn,
                mission_id=mission_id,
                name=name,
                sprint_id=sprint_id,
                status=normalized_status,
            )
        except (ValueError, sqlite3.IntegrityError) as exc:
            typer.echo(f"Failed to add mission: {exc}")
            raise typer.Exit(code=1) from exc

    typer.echo(f"Mission {mission_id} added with status {normalized_status}.")


@session_app.command("log")
def session_log(
    ctx: typer.Context,
    action: str = typer.Option(
        ...,
        "--type",
        "-t",
        help=f"Session action ({_SESSION_ACTIONS_DISPLAY})",
        callback=_validate_session_action,
    ),
    mission: str | None = typer.Option(
        None,
        "--mission",
        "-m",
        help="Optional mission identifier to associate with the session",
    ),
    summary: str = typer.Option(
        ...,
        "--summary",
        "-s",
        prompt="Summary",
        help="Short description of the session activity",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Agent responsible for the session (defaults to CMOS_AGENT or current user)",
    ),
    details: str | None = typer.Option(
        None,
        "--details",
        "-d",
        help="Optional extended details or metadata",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    mission_value = mission.strip() if mission and mission.strip() else None
    agent_value = agent.strip() if agent and agent.strip() else _default_agent()
    summary_value = summary.strip()
    if not summary_value:
        raise typer.BadParameter("Summary cannot be empty.")
    details_value = details.strip() if details and details.strip() else None

    with db_commands.connect(db_path) as conn:
        try:
            session_id = db_commands.log_session(
                conn,
                action=action,
                mission_id=mission_value,
                agent=agent_value,
                summary=summary_value,
                details=details_value,
            )
        except ValueError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc

    typer.echo(f"Logged session {session_id} ({action}).")


@session_app.command("list")
def session_list(
    ctx: typer.Context,
    mission: str | None = typer.Option(
        None,
        "--mission",
        "-m",
        help="Filter to sessions for a specific mission identifier",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        "-l",
        min=0,
        help="Maximum number of sessions to display (0 shows all)",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    mission_value = mission.strip() if mission and mission.strip() else None

    with db_commands.connect(db_path) as conn:
        sessions = db_commands.list_sessions(conn, mission_id=mission_value)

    if limit:
        sessions = sessions[:limit]

    if not sessions:
        typer.echo("No sessions found.")
        raise typer.Exit(code=0)

    for line in _format_sessions_table(sessions):
        typer.echo(line)


@session_app.command("show")
def session_show(
    ctx: typer.Context,
    session_id: int = typer.Argument(..., help="Numeric identifier of the session to display"),
) -> None:
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        session = db_commands.get_session(conn, session_id=session_id)

    if session is None:
        typer.echo(f"Session {session_id} not found.")
        raise typer.Exit(code=1)

    typer.echo(f"ID: {session.id}")
    typer.echo(f"Timestamp: {session.ts}")
    typer.echo(f"Mission: {session.mission_id or '-'}")
    typer.echo(f"Action: {session.action}")
    typer.echo(f"Agent: {session.agent or '-'}")
    typer.echo(f"Summary: {session.summary or '-'}")
    typer.echo("Details:")
    typer.echo(session.details or "-")


@hook_app.command("install")
def hook_install(
    ctx: typer.Context,
    path: Path = typer.Option(
        Path(".git/hooks/post-commit"),
        "--path",
        "-p",
        help="Destination for the post-commit hook script (default: .git/hooks/post-commit)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing hook if present",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    repo_root = Path.cwd()
    if db_path.is_absolute():
        db_path_abs = db_path.resolve()
    else:
        db_path_abs = (repo_root / db_path).resolve()
    db_path_literal = json.dumps(str(db_path_abs))
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        typer.echo("Git directory not found. Run this command from the repository root.")
        raise typer.Exit(code=1)

    hook_path = path if path.is_absolute() else repo_root / path
    hooks_dir = hook_path.parent
    hooks_dir.mkdir(parents=True, exist_ok=True)

    if hook_path.exists() and not force:
        typer.echo(f"Hook already exists at {hook_path}. Use --force to overwrite.")
        raise typer.Exit(code=1)

    script_template = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        from __future__ import annotations

        import json
        import sqlite3
        import subprocess
        import sys
        from pathlib import Path

        REPO_ROOT = Path(__file__).resolve().parent.parent.parent
        DB_PATH = Path(__DB_PATH__)


        def _run(cmd: list[str]) -> str:
            return subprocess.check_output(cmd, text=True, cwd=str(REPO_ROOT)).strip()


        def _changed_files() -> list[str]:
            output = _run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
            return [line for line in output.splitlines() if line]


        def _active_mission() -> str | None:
            if not DB_PATH.exists():
                return None
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.row_factory = sqlite3.Row
                query = \"\"\"
                    SELECT id
                    FROM missions
                    WHERE status = ?
                    ORDER BY datetime(created_at) ASC, id ASC
                    LIMIT 1
                \"\"\"
                row = conn.execute(query, ("In Progress",)).fetchone()
                if row is None:
                    row = conn.execute(query, ("Current",)).fetchone()
                return row["id"] if row else None
            finally:
                conn.close()


        def main() -> None:
            try:
                commit_hash = _run(["git", "rev-parse", "HEAD"])
                commit_message = _run(["git", "log", "-1", "--pretty=%s", "HEAD"])
                files = _changed_files()
                mission_id = _active_mission()

                details = {"hash": commit_hash, "files": files}
                if mission_id:
                    details["mission"] = mission_id

                cmd = [
                    sys.executable,
                    "-m",
                    "cmosctl",
                    "session",
                    "log",
                    "--type",
                    "commit",
                    "--agent",
                    "git-hook",
                    "--summary",
                    commit_message,
                    "--details",
                    json.dumps(details),
                ]
                if mission_id:
                    cmd.extend(["--mission", mission_id])

                subprocess.run(
                    cmd,
                    cwd=str(REPO_ROOT),
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                sys.stderr.write("[cmos hook] failed to log commit session\\n")
                if exc.stderr:
                    sys.stderr.write(exc.stderr + "\\n")
            except Exception as exc:  # pragma: no cover - defensive fallback
                sys.stderr.write(f"[cmos hook] unexpected error: {exc}\\n")


        if __name__ == "__main__":
            main()
        """
    )

    script = script_template.replace("__DB_PATH__", db_path_literal)

    hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)
    typer.echo(f"Installed post-commit hook at {hook_path}")


def _load_missions_from_backlog(backlog_path: Path) -> list[dict[str, str | None]]:
    if not backlog_path.exists():
        raise FileNotFoundError(f"Backlog file not found at {backlog_path}")

    missions: list[dict[str, str | None]] = []
    with backlog_path.open("r", encoding="utf-8") as handle:
        for doc in yaml.safe_load_all(handle):
            if not isinstance(doc, dict):
                continue
            domain_fields = doc.get("domainFields")
            if not isinstance(domain_fields, dict):
                continue
            sprints = domain_fields.get("sprints") or []
            for sprint in sprints:
                if not isinstance(sprint, dict):
                    continue
                sprint_id = sprint.get("sprintId")
                for raw_mission in sprint.get("missions") or []:
                    if not isinstance(raw_mission, dict):
                        continue
                    mission_id = raw_mission.get("id")
                    name = raw_mission.get("name")
                    status = raw_mission.get("status", "Queued")
                    normalized_status = STATUS_NORMALIZATION.get(status)
                    if normalized_status is None:
                        raise ValueError(f"Mission {mission_id!r} uses unsupported status {status!r}.")
                    if not mission_id or not name:
                        raise ValueError("Mission entries must include 'id' and 'name'.")
                    missions.append(
                        {
                            "id": mission_id,
                            "sprint_id": sprint_id,
                            "name": name,
                            "status": normalized_status,
                            "completed_at": raw_mission.get("completed_at"),
                            "notes": raw_mission.get("notes"),
                        }
                    )

    return missions


def _extract_header(text: str) -> str:
    header_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            header_lines.append(line)
        else:
            break
    return "\n".join(header_lines)


def _load_backlog_template(backlog_path: Path) -> BacklogTemplate:
    if not backlog_path.exists():
        raise FileNotFoundError(f"Backlog file not found at {backlog_path}")

    raw_text = backlog_path.read_text(encoding="utf-8")
    header = _extract_header(raw_text)
    docs = list(yaml.safe_load_all(raw_text))
    if not docs:
        raise ValueError(f"Backlog file at {backlog_path} is empty.")
    if len(docs) < 2:
        docs.append({})

    sprint_map: dict[str, dict[str, Any]] = {}
    sprint_order: list[str] = []
    second_doc = docs[1] if isinstance(docs[1], dict) else {}
    domain_fields = second_doc.get("domainFields") if isinstance(second_doc, dict) else {}
    if isinstance(domain_fields, dict):
        for sprint in domain_fields.get("sprints") or []:
            if not isinstance(sprint, dict):
                continue
            sprint_id = sprint.get("sprintId")
            if sprint_id and sprint_id not in sprint_map:
                sprint_map[sprint_id] = sprint
                sprint_order.append(sprint_id)

    return BacklogTemplate(header=header, docs=docs, sprint_order=sprint_order, sprint_map=sprint_map)


def _derive_sprint_status(original_status: str | None, mission_statuses: Sequence[str | None]) -> str:
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


def _apply_missions_to_backlog(template: BacklogTemplate, missions: Sequence[db_commands.Mission]) -> None:
    if not template.docs:
        return

    if len(template.docs) < 2 or not isinstance(template.docs[1], dict):
        template.docs.append({"domainFields": {"sprints": []}})
    second_doc = template.docs[1]
    if not isinstance(second_doc, dict):
        second_doc = {}
        template.docs[1] = second_doc

    domain_fields = second_doc.setdefault("domainFields", {})
    if not isinstance(domain_fields, dict):
        domain_fields = {}
        second_doc["domainFields"] = domain_fields

    sprints_list = domain_fields.setdefault("sprints", [])
    if not isinstance(sprints_list, list):
        sprints_list = []
        domain_fields["sprints"] = sprints_list

    mission_entry_map: dict[str, dict[str, Any]] = {}
    for sprint in sprints_list:
        if not isinstance(sprint, dict):
            continue
        sprint_id = sprint.get("sprintId")
        if sprint_id and sprint_id not in template.sprint_map:
            template.sprint_map[sprint_id] = sprint
        if sprint_id and sprint_id not in template.sprint_order:
            template.sprint_order.append(sprint_id)
        missions_list = sprint.setdefault("missions", [])
        if not isinstance(missions_list, list):
            missions_list = []
            sprint["missions"] = missions_list
        for item in missions_list:
            if isinstance(item, dict):
                mission_id = item.get("id")
                if mission_id:
                    mission_entry_map[mission_id] = item

    mission_status_lookup = {mission.id: mission.status for mission in missions}

    for mission in missions:
        sprint_id = mission.sprint_id or "Unassigned"
        sprint = template.sprint_map.get(sprint_id)
        if sprint is None:
            sprint = {
                "sprintId": sprint_id,
                "title": mission.sprint_id or sprint_id,
                "focus": "",
                "status": "Queued",
                "missions": [],
            }
            sprints_list.append(sprint)
            template.sprint_map[sprint_id] = sprint
        if sprint_id not in template.sprint_order:
            template.sprint_order.append(sprint_id)

        missions_list = sprint.setdefault("missions", [])
        if not isinstance(missions_list, list):
            missions_list = []
            sprint["missions"] = missions_list

        mission_entry = mission_entry_map.get(mission.id)
        if mission_entry is None:
            mission_entry = {"id": mission.id, "name": mission.name}
            missions_list.append(mission_entry)
            mission_entry_map[mission.id] = mission_entry
        else:
            mission_entry["name"] = mission.name

        mission_entry["status"] = mission.status
        if mission.completed_at:
            mission_entry["completed_at"] = mission.completed_at
        else:
            mission_entry.pop("completed_at", None)

        if mission.notes:
            mission_entry["notes"] = mission.notes
        else:
            mission_entry.pop("notes", None)

    for sprint in sprints_list:
        missions_list = sprint.get("missions") or []
        statuses = [
            mission_status_lookup.get(item.get("id"), item.get("status"))
            for item in missions_list
            if isinstance(item, dict)
        ]
        sprint["status"] = _derive_sprint_status(sprint.get("status"), statuses)


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


def _session_to_export_record(session: db_commands.Session) -> dict[str, Any]:
    record: dict[str, Any] = {
        "ts": session.ts,
        "action": session.action,
        "status": SESSION_STATUS_FROM_ACTION.get(session.action, session.action),
    }
    if session.mission_id:
        record["mission"] = session.mission_id
    if session.agent:
        record["agent"] = session.agent
    if session.summary:
        record["summary"] = session.summary
    details = _parse_details_field(session.details)
    if details is not None:
        record["details"] = details
    return record


def _load_sessions_from_jsonl(source: Path) -> list[dict[str, Any]]:
    if not source.exists():
        raise FileNotFoundError(f"Sessions file not found at {source}")

    sessions: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {index}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Line {index} does not contain a JSON object.")
            sessions.append(payload)
    return sessions


def _mission_summary(mission: db_commands.Mission | None) -> dict[str, Any] | None:
    if mission is None:
        return None
    return {
        "id": mission.id,
        "name": mission.name,
        "status": mission.status,
        "sprint": mission.sprint_id,
        "completed_at": mission.completed_at,
        "notes": mission.notes,
    }


def _build_status_snapshot(
    db_path: Path,
    *,
    backlog_path: Path | None = None,
    recent_limit: int = 5,
) -> dict[str, Any]:
    with db_commands.connect(db_path) as conn:
        missions = db_commands.list_missions(conn)
        active_mission = db_commands.get_in_progress_mission(conn)
        current_mission = active_mission or db_commands.get_current_mission(conn)
        next_candidate = db_commands.get_next_queued_mission(conn)
        sessions = db_commands.list_sessions(conn)

    template: BacklogTemplate | None = None
    if backlog_path and backlog_path.exists():
        try:
            template = _load_backlog_template(backlog_path)
        except (FileNotFoundError, ValueError):
            template = None

    sprint_meta: dict[str, dict[str, Any]] = {}
    sprint_order: list[str] = []
    if template is not None:
        sprint_order = list(template.sprint_order)
        for sprint_id, sprint in template.sprint_map.items():
            sprint_meta[sprint_id] = {
                "title": sprint.get("title"),
                "focus": sprint.get("focus"),
                "status": sprint.get("status"),
            }

    mission_groups: dict[str, list[db_commands.Mission]] = defaultdict(list)
    for mission in missions:
        sprint_id = mission.sprint_id or "Unassigned"
        mission_groups[sprint_id].append(mission)
        if sprint_id not in sprint_meta:
            sprint_meta[sprint_id] = {
                "title": mission.sprint_id or sprint_id,
                "focus": None,
                "status": None,
            }
        if sprint_id not in sprint_order:
            sprint_order.append(sprint_id)

    totals = Counter(mission.status for mission in missions)
    sprint_summaries: list[dict[str, Any]] = []
    for sprint_id in sprint_order:
        bucket = mission_groups.get(sprint_id, [])
        counts = Counter(m.status for m in bucket)
        aggregated_status = _derive_sprint_status(
            sprint_meta.get(sprint_id, {}).get("status"),
            [mission.status for mission in bucket],
        )
        sprint_summaries.append(
            {
                "sprint_id": sprint_id,
                "title": sprint_meta.get(sprint_id, {}).get("title"),
                "focus": sprint_meta.get(sprint_id, {}).get("focus"),
                "status": aggregated_status,
                "counts": dict(counts),
                "missions": [
                    {
                        "id": mission.id,
                        "name": mission.name,
                        "status": mission.status,
                        "completed_at": mission.completed_at,
                        "notes": mission.notes,
                    }
                    for mission in bucket
                ],
            }
        )

    sessions_sorted = sorted(sessions, key=lambda entry: (entry.ts, entry.id), reverse=True)
    recent_sessions = [
        {
            "id": entry.id,
            "ts": entry.ts,
            "mission": entry.mission_id,
            "action": entry.action,
            "status": SESSION_STATUS_FROM_ACTION.get(entry.action, entry.action),
            "agent": entry.agent,
            "summary": entry.summary,
        }
        for entry in sessions_sorted[: recent_limit if recent_limit > 0 else None]
    ]

    next_mission = next_candidate
    if current_mission and next_candidate and current_mission.id == next_candidate.id:
        next_mission = None

    return {
        "generated_at": db_commands.utc_now_iso(),
        "totals": {
            "missions": len(missions),
            "sessions": len(sessions),
            "by_status": dict(totals),
        },
        "active_mission": _mission_summary(active_mission),
        "current_mission": _mission_summary(current_mission),
        "next_mission": _mission_summary(next_mission),
        "sprints": sprint_summaries,
        "recent_sessions": recent_sessions,
    }


def _export_backlog_file(
    db_path: Path,
    *,
    output: Path,
    template_path: Path,
) -> int:
    template = _load_backlog_template(template_path)
    with db_commands.connect(db_path) as conn:
        missions = db_commands.list_missions(conn)

    _apply_missions_to_backlog(template, missions)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        if template.header:
            handle.write(template.header.rstrip() + "\n")
        yaml.safe_dump_all(template.docs, handle, sort_keys=False)
    return len(missions)


def _export_sessions_file(
    db_path: Path,
    *,
    output: Path,
) -> int:
    with db_commands.connect(db_path) as conn:
        sessions = db_commands.list_sessions(conn)

    sessions_sorted = sorted(sessions, key=lambda entry: (entry.ts, entry.id))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for session in sessions_sorted:
            record = _session_to_export_record(session)
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
    return len(sessions_sorted)


@export_app.command("backlog")
def export_backlog(
    ctx: typer.Context,
    output: Path = typer.Option(
        DEFAULT_BACKLOG_PATH,
        "--output",
        "-o",
        help="Destination for the exported backlog YAML file (default: cmos/missions/backlog.yaml)",
    ),
    template: Path = typer.Option(
        DEFAULT_BACKLOG_PATH,
        "--template",
        "-t",
        help="Backlog template used for metadata (default: cmos/missions/backlog.yaml)",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    try:
        mission_count = _export_backlog_file(db_path, output=output, template_path=template)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"Exported {mission_count} missions to {output}")


@export_app.command("sessions")
def export_sessions(
    ctx: typer.Context,
    output: Path = typer.Option(
        DEFAULT_SESSIONS_PATH,
        "--output",
        "-o",
        help="Destination for the exported sessions JSONL file (default: cmos/SESSIONS.jsonl)",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    session_count = _export_sessions_file(db_path, output=output)
    typer.echo(f"Exported {session_count} sessions to {output}")


@export_app.command("all")
def export_all(
    ctx: typer.Context,
    backlog_output: Path = typer.Option(
        DEFAULT_BACKLOG_PATH,
        "--backlog-output",
        help="Destination for backlog YAML export (default: cmos/missions/backlog.yaml)",
    ),
    sessions_output: Path = typer.Option(
        DEFAULT_SESSIONS_PATH,
        "--sessions-output",
        help="Destination for sessions JSONL export (default: cmos/SESSIONS.jsonl)",
    ),
    template: Path = typer.Option(
        DEFAULT_BACKLOG_PATH,
        "--template",
        "-t",
        help="Backlog template used for metadata (default: cmos/missions/backlog.yaml)",
    ),
) -> None:
    db_path = _ensure_context(ctx)
    try:
        mission_count = _export_backlog_file(db_path, output=backlog_output, template_path=template)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    session_count = _export_sessions_file(db_path, output=sessions_output)
    typer.echo(
        f"Exported backlog ({mission_count} missions) to {backlog_output} "
        f"and sessions ({session_count} entries) to {sessions_output}"
    )


@db_app.command("import")
def db_import(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Exported backlog (.yaml/.yml) or sessions (.jsonl) file to import"),
) -> None:
    if not source.exists():
        typer.echo(f"File not found: {source}")
        raise typer.Exit(code=1)

    db_path = _ensure_context(ctx)
    suffix = source.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        try:
            missions = _load_missions_from_backlog(source)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        if not missions:
            typer.echo("No missions found in backlog file; database not modified.")
            raise typer.Exit(code=1)
        with db_commands.connect(db_path) as conn:
            db_commands.replace_missions(conn, missions)
        typer.echo(f"Imported {len(missions)} missions from {source}")
        return

    if suffix == ".jsonl":
        try:
            sessions = _load_sessions_from_jsonl(source)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        if not sessions:
            typer.echo("No sessions found in JSONL file; database not modified.")
            raise typer.Exit(code=1)
        try:
            with db_commands.connect(db_path) as conn:
                db_commands.replace_sessions(conn, sessions)
        except ValueError as exc:
            typer.echo(f"Failed to import sessions: {exc}")
            raise typer.Exit(code=1) from exc
        typer.echo(f"Imported {len(sessions)} sessions from {source}")
        return

    typer.echo("Unsupported file type. Provide a .yaml/.yml backlog or .jsonl sessions file.")
    raise typer.Exit(code=1)


@app.command("status")
def status_command(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show mission breakdown for each sprint."),
    backlog: Path = typer.Option(
        DEFAULT_BACKLOG_PATH,
        "--backlog",
        help="Backlog template for sprint metadata (default: cmos/missions/backlog.yaml)",
    ),
    recent: int = typer.Option(5, "--recent", help="Number of recent sessions to summarize (default: 5)"),
) -> None:
    db_path = _ensure_context(ctx)
    backlog_path = backlog if backlog.exists() else None
    snapshot = _build_status_snapshot(db_path, backlog_path=backlog_path, recent_limit=recent)

    active = snapshot["active_mission"]
    current = snapshot["current_mission"]
    next_mission = snapshot["next_mission"]

    if active:
        typer.echo(f"Active mission: {active['id']} [{active['status']}] - {active['name']}")
    elif current:
        typer.echo(f"Current mission: {current['id']} [{current['status']}] - {current['name']}")
    else:
        typer.echo("No mission is currently active.")

    if next_mission:
        typer.echo(f"Next mission: {next_mission['id']} [{next_mission['status']}] - {next_mission['name']}")

    totals = snapshot["totals"]
    counts_summary = ", ".join(f"{status}: {count}" for status, count in sorted(totals["by_status"].items()))
    if counts_summary:
        typer.echo(f"Missions total: {totals['missions']} ({counts_summary})")
    else:
        typer.echo(f"Missions total: {totals['missions']}")
    typer.echo(f"Sessions logged: {totals['sessions']}")

    typer.echo("Sprint overview:")
    for sprint in snapshot["sprints"]:
        title = sprint["title"] or sprint["sprint_id"]
        counts = sprint["counts"]
        counts_str = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
        summary_line = f"- {sprint['sprint_id']} ({title}) [{sprint['status']}]"
        if counts_str:
            summary_line += f" {counts_str}"
        typer.echo(summary_line)
        if verbose:
            for mission in sprint["missions"]:
                details = f"    • {mission['id']} [{mission['status']}] {mission['name']}"
                if mission["status"] == "Completed" and mission.get("completed_at"):
                    details += f" (completed {mission['completed_at']})"
                elif mission["status"] == "Blocked" and mission.get("notes"):
                    details += f" – {mission['notes']}"
                typer.echo(details)

    if verbose and snapshot["recent_sessions"]:
        typer.echo("Recent sessions:")
        for session in snapshot["recent_sessions"]:
            summary = session.get("summary") or "-"
            mission_id = session.get("mission") or "-"
            typer.echo(f"  - [{session['ts']}] {session['action']} {mission_id}: {summary}")


@app.command("context")
def context_command(
    ctx: typer.Context,
    backlog: Path = typer.Option(
        DEFAULT_BACKLOG_PATH,
        "--backlog",
        help="Backlog template for sprint metadata (default: cmos/missions/backlog.yaml)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional destination file for context JSON (default: print to stdout)",
    ),
    recent: int = typer.Option(5, "--recent", help="Number of recent sessions to include (default: 5)"),
) -> None:
    db_path = _ensure_context(ctx)
    backlog_path = backlog if backlog.exists() else None
    snapshot = _build_status_snapshot(db_path, backlog_path=backlog_path, recent_limit=recent)

    project_context: dict[str, Any] = {}
    if DEFAULT_PROJECT_CONTEXT_PATH.exists():
        try:
            with DEFAULT_PROJECT_CONTEXT_PATH.open("r", encoding="utf-8") as handle:
                project_context = json.load(handle)
        except json.JSONDecodeError:
            project_context = {}

    payload: dict[str, Any] = {
        "generated_at": snapshot["generated_at"],
        "project": project_context.get("project"),
        "active_mission": snapshot["active_mission"],
        "current_mission": snapshot["current_mission"],
        "next_mission": snapshot["next_mission"],
        "mission_totals": snapshot["totals"],
        "sprints": [
            {
                "sprint_id": sprint["sprint_id"],
                "title": sprint["title"],
                "focus": sprint["focus"],
                "status": sprint["status"],
                "counts": sprint["counts"],
            }
            for sprint in snapshot["sprints"]
        ],
        "recent_sessions": snapshot["recent_sessions"],
    }

    if "working_memory" in project_context:
        payload["working_memory"] = project_context["working_memory"]
    if "technical_context" in project_context:
        payload["technical_context"] = project_context["technical_context"]
    if "ai_instructions" in project_context:
        payload["ai_instructions"] = project_context["ai_instructions"]

    json_output = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_output + "\n", encoding="utf-8")
        typer.echo(f"Wrote context to {output}")
    else:
        typer.echo(json_output)


@mission_app.command("sync-backlog")
def mission_sync_backlog(
    ctx: typer.Context,
    source: Path = typer.Option(
        Path("cmos/missions/backlog.yaml"),
        "--source",
        "-s",
        help="Path to the backlog YAML file (default: cmos/missions/backlog.yaml)",
    ),
) -> None:
    try:
        missions = _load_missions_from_backlog(source)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(f"Backlog parsing error: {exc}")
        raise typer.Exit(code=1) from exc

    if not missions:
        typer.echo("No missions found in backlog; database left unchanged.")
        raise typer.Exit(code=1)

    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        db_commands.replace_missions(conn, missions)

    status_counts = Counter(mission["status"] for mission in missions)
    summary = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))
    typer.echo(f"Seeded {len(missions)} missions from {source} into {db_path}.")
    typer.echo(f"Status distribution -> {summary}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        app(
            args=list(argv) if argv is not None else None,
            prog_name="cmosctl",
            standalone_mode=False,
        )
    except typer.Exit as exc:
        return exc.exit_code
    except Exception as exc:  # pragma: no cover - top-level guard
        typer.echo(f"Error: {exc}", err=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
