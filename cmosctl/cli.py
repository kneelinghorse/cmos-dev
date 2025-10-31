from __future__ import annotations

import getpass
import json
import os
import sqlite3
import sys
import textwrap
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

import typer
import yaml

from . import db as db_commands

app = typer.Typer(help="CMOS command-line interface", add_completion=False, no_args_is_help=True)
mission_app = typer.Typer(help="Mission management commands", add_completion=False)
db_app = typer.Typer(help="Database maintenance commands", add_completion=False)
session_app = typer.Typer(help="Session logging commands", add_completion=False)
hook_app = typer.Typer(help="Git hook utilities", add_completion=False)

app.add_typer(db_app, name="db")
app.add_typer(mission_app, name="mission")
app.add_typer(session_app, name="session")
app.add_typer(hook_app, name="hook")

STATUS_NORMALIZATION = {
    "Queued": "Queued",
    "Current": "Current",
    "In Progress": "In Progress",
    "Completed": "Completed",
    "Blocked": "Blocked",
    "Planned": "Queued",
}


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
    db_path = _ensure_context(ctx)
    with db_commands.connect(db_path) as conn:
        try:
            db_commands.add_mission(
                conn,
                mission_id=mission_id,
                name=name,
                sprint_id=sprint_id,
                status=status,
            )
        except (ValueError, sqlite3.IntegrityError) as exc:
            typer.echo(f"Failed to add mission: {exc}")
            raise typer.Exit(code=1) from exc

    typer.echo(f"Mission {mission_id} added with status {status}.")


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
