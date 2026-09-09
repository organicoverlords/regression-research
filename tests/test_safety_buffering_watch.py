import datetime as dt
import json
import sqlite3
from pathlib import Path

from tools.safety_buffering_watch import (
    ToolPlaneState,
    append_marker,
    iter_new_transport,
    read_thread_rows,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_tool_plane_state_distinguishes_live_child_from_no_child() -> None:
    state = ToolPlaneState()
    state.ingest({"at": "2026-09-07T20:00:00Z", "event": "request_start"})
    state.ingest({"at": "2026-09-07T20:00:00.010Z", "event": "process_started", "process_id": "p1", "pid": 1})
    assert state.snapshot()["live_process_count"] == 1
    state.ingest({"at": "2026-09-07T20:00:02Z", "event": "process_exit_observed", "process_id": "p1", "pid": 1})
    assert state.snapshot()["live_process_count"] == 0


def test_snapshot_clamps_future_clock_skew_to_zero() -> None:
    state = ToolPlaneState()
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    state.ingest({"at": future, "event": "request_start"})
    snap = state.snapshot()
    assert snap["seconds_since_last_target_event"] == 0.0
    assert snap["seconds_since_last_request_start"] == 0.0


def test_iter_new_transport_filters_caller_and_preserves_partial_line(tmp_path: Path) -> None:
    transport = tmp_path / "transport.jsonl"
    good = {"at": "2026-09-07T20:00:00Z", "caller_id": "caller_x", "event": "request_start"}
    other = {"at": "2026-09-07T20:00:01Z", "caller_id": "caller_y", "event": "request_start"}
    transport.write_bytes((json.dumps(good) + "\n" + json.dumps(other) + "\n" + '{"caller_id":"caller_x"').encode())
    offset, rows, truncated = iter_new_transport(transport, 0, "caller_x")
    assert not truncated
    assert rows == [good]
    assert offset < transport.stat().st_size
    with transport.open("ab") as f:
        f.write(b',"event":"response_finish"}\n')
    offset2, rows2, _ = iter_new_transport(transport, offset, "caller_x")
    assert offset2 == transport.stat().st_size
    assert rows2[0]["event"] == "response_finish"


def test_read_thread_rows_is_thread_scoped_and_incremental(tmp_path: Path) -> None:
    db = tmp_path / "logs.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "create table logs (id integer primary key,ts integer,ts_nanos integer,level text,target text,file text,line integer,process_uuid text,thread_id text,feedback_log_body text)"
    )
    con.execute("insert into logs values (1,1,0,'INFO','a','x',1,'p','thread_x','one')")
    con.execute("insert into logs values (2,2,0,'INFO','b','y',2,'p','thread_y','other')")
    con.execute("insert into logs values (3,3,0,'INFO','c','z',3,'p','thread_x','three')")
    con.commit()
    con.close()
    rows = read_thread_rows(db, "thread_x", 1)
    assert [r["id"] for r in rows] == [3]
    assert rows[0]["feedback_log_body"] == "three"


def test_append_marker_is_jsonl_and_does_not_require_live_watch(tmp_path: Path) -> None:
    out = tmp_path / "capture.jsonl"
    append_marker(out, "banner_on", "screen observed", "caller_x", "thread_x")
    row = json.loads(out.read_text(encoding="utf-8").strip())
    assert row["capture_kind"] == "operator_marker"
    assert row["label"] == "banner_on"
    assert row["note"] == "screen observed"
