import json
import os
import shutil
import subprocess
import sys

import pytest
from pathlib import Path

from tools import bootstrap_read_loop as bootstrap_read_loop
from tools.memory_recent_projection import write_recent_projection


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "bootstrap_read_loop.py"


def _write_fake_atlas(root: Path) -> None:
    tools = root / "tools"
    tools.mkdir(parents=True)
    (tools / "stack_atlas.py").write_text(
        "import json\n"
        "print(json.dumps({"
        "'bootstrap_warning': {'status': 'READ_TO_END'}, "
        "'schema': 'bootstrap.v1', "
        "'generated_at': '2026-09-09T09:00:00+00:00', "
        "'source_marker': 'alternate-root', "
        "'memory_overview': {"
        "'recent': [{'id':'materialized-old','timestamp':'2026-09-09T09:00:00+00:00','title':'materialized old'}], "
        "'timeline_materialized': {'as_of':'2026-09-09T09:00:00+00:00','read_mode':'MATERIALIZED_ONLY'}"
        "}, "
        "'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}"
        "}))\n",
        encoding="utf-8",
    )


def _memory_files(root: Path, tmp_path: Path) -> tuple[Path, Path]:
    seed = root / 'memory' / 'memory-bank.jsonl'
    overlay = tmp_path / 'local-memory' / 'memory-bank.local.jsonl'
    seed.parent.mkdir(parents=True, exist_ok=True)
    overlay.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text('', encoding='utf-8')
    overlay.write_text('', encoding='utf-8')
    return seed, overlay


def _run_once(
    alternate: Path,
    overlay: Path,
    *,
    quiet: bool = True,
    skip_if_fresh_seconds: float | None = None,
    heartbeat_if_older_than_seconds: float | None = None,
    atlas_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['VAULT_MEMORY_LOCAL_BANK'] = str(overlay)
    command = [sys.executable, str(SCRIPT), '--once', '--repo-root', str(alternate)]
    if atlas_path is not None:
        command.extend(['--atlas-path', str(atlas_path)])
    if quiet:
        command.append('--quiet')
    if skip_if_fresh_seconds is not None:
        command.extend(['--skip-if-fresh-seconds', str(skip_if_fresh_seconds)])
    if heartbeat_if_older_than_seconds is not None:
        command.extend(['--heartbeat-if-older-than-seconds', str(heartbeat_if_older_than_seconds)])
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=20,
        env=env,
    )


def test_once_uses_explicit_repo_root(tmp_path: Path) -> None:
    alternate = tmp_path / "alternate"
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)

    cp = _run_once(alternate, overlay, quiet=False)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip("\ufeff"))
    assert payload["schema"] == "bootstrap.v1"
    assert payload["source_marker"] == "alternate-root"
    assert payload["bootstrap_end"]["status"] == "COMPLETE"
    assert json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8')) == payload
    assert not list((alternate / '.state' / 'bootstrap').glob('*.tmp'))


def test_once_can_run_deployed_atlas_outside_repo_root(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    atlas = runtime / 'stack_atlas.py'
    atlas.write_text(
        "import json, os\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':'2026-09-11T11:00:00+00:00',"
        "'source_marker':'runtime-atlas','root_override':os.environ.get('STACK_ATLAS_ROOT_OVERRIDE'),"
        "'pythonpath':os.environ.get('PYTHONPATH',''),'memory_overview':{'recent':[]},"
        "'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    cp = _run_once(alternate, overlay, quiet=False, atlas_path=atlas)
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    assert payload['source_marker'] == 'runtime-atlas'
    assert Path(payload['root_override']) == alternate.resolve()
    assert str(alternate.resolve()) in payload['pythonpath'].split(os.pathsep)


def test_deployed_atlas_refreshes_from_cached_origin_main_not_feature_head_or_dirty_worktree(tmp_path: Path) -> None:
    alternate = tmp_path / 'repo'
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    _write_fake_atlas(alternate)
    subprocess.run(['git', 'init', '-q'], cwd=alternate, check=True)
    subprocess.run(['git', 'add', 'tools/stack_atlas.py'], cwd=alternate, check=True)
    subprocess.run(
        ['git', '-c', 'user.name=Bootstrap Test', '-c', 'user.email=bootstrap@example.invalid',
         'commit', '-q', '-m', 'canonical atlas'],
        cwd=alternate, check=True,
    )
    canonical = alternate / 'tools' / 'stack_atlas.py'
    canonical_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=alternate, text=True).strip()
    subprocess.run(['git', 'update-ref', 'refs/remotes/origin/main', canonical_commit], cwd=alternate, check=True)
    source_bytes = subprocess.check_output(
        ['git', 'show', 'refs/remotes/origin/main:tools/stack_atlas.py'], cwd=alternate
    )
    canonical.write_text(
        canonical.read_text(encoding='utf-8').replace('alternate-root', 'feature-branch-head'),
        encoding='utf-8',
    )
    subprocess.run(['git', 'add', 'tools/stack_atlas.py'], cwd=alternate, check=True)
    subprocess.run(
        ['git', '-c', 'user.name=Bootstrap Test', '-c', 'user.email=bootstrap@example.invalid',
         'commit', '-q', '-m', 'feature branch atlas must not deploy'],
        cwd=alternate, check=True,
    )
    canonical.write_text(canonical.read_text(encoding='utf-8') + '\n# dirty-working-tree\n', encoding='utf-8')
    atlas = runtime / 'stack_atlas.py'
    atlas.write_text(
        "import json\nprint(json.dumps({'schema':'bootstrap.v1','generated_at':'2026-09-11T11:00:00+00:00',"
        "'source_marker':'stale-runtime','memory_overview':{'recent':[]},"
        "'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)

    cp = _run_once(alternate, overlay, quiet=False, atlas_path=atlas)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    assert payload['source_marker'] == 'alternate-root'
    assert atlas.read_bytes() == source_bytes
    assert 'feature-branch-head' in canonical.read_text(encoding='utf-8')
    assert 'dirty-working-tree' in canonical.read_text(encoding='utf-8')



def test_deployed_byte_repair_falls_back_when_atomic_replace_is_denied(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / 'bootstrap_read_loop.py'
    destination.write_bytes(b'old-runtime-bytes\n')
    desired = b'new-committed-bytes\n'

    def deny_replace(*_args, **_kwargs):
        raise PermissionError(5, 'destination is held without delete sharing')

    monkeypatch.setattr(bootstrap_read_loop, '_replace_snapshot', deny_replace)
    monkeypatch.setattr(bootstrap_read_loop.os, 'name', 'nt')

    assert bootstrap_read_loop._replace_deployed_file_bytes(destination, desired) is True
    assert destination.read_bytes() == desired


def test_deployed_producer_bundle_repairs_from_cached_origin_main_not_feature_head(tmp_path: Path) -> None:
    alternate = tmp_path / 'repo'
    runtime = tmp_path / 'runtime'
    tools = alternate / 'tools'
    _write_fake_atlas(alternate)
    runtime.mkdir()

    producer_source = REPO_ROOT / 'tools' / 'bootstrap_read_loop.py'
    helper_source = REPO_ROOT / 'tools' / 'memory_recent_projection.py'
    live_swarm_source = REPO_ROOT / 'tools' / 'live_swarm.py'
    slot_registry_source = REPO_ROOT / 'tools' / 'recurring_slot_registry.py'
    shutil.copy2(producer_source, tools / 'bootstrap_read_loop.py')
    shutil.copy2(helper_source, tools / 'memory_recent_projection.py')
    shutil.copy2(live_swarm_source, tools / 'live_swarm.py')
    shutil.copy2(slot_registry_source, tools / 'recurring_slot_registry.py')
    subprocess.run(['git', 'init', '-q'], cwd=alternate, check=True)
    subprocess.run(['git', 'add', 'tools'], cwd=alternate, check=True)
    subprocess.run(
        ['git', '-c', 'user.name=Bootstrap Test', '-c', 'user.email=bootstrap@example.invalid',
         'commit', '-q', '-m', 'canonical bootstrap bundle'],
        cwd=alternate, check=True,
    )
    canonical_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=alternate, text=True).strip()
    subprocess.run(['git', 'update-ref', 'refs/remotes/origin/main', canonical_commit], cwd=alternate, check=True)
    deployed_source = {
        name: subprocess.check_output(['git', 'show', f'refs/remotes/origin/main:tools/{name}'], cwd=alternate)
        for name in ('bootstrap_read_loop.py', 'memory_recent_projection.py', 'stack_atlas.py', 'live_swarm.py', 'recurring_slot_registry.py')
    }

    # Commit a different feature HEAD. The scheduled runtime must ignore it.
    (tools / 'stack_atlas.py').write_text(
        (tools / 'stack_atlas.py').read_text(encoding='utf-8').replace('alternate-root', 'feature-branch-head'),
        encoding='utf-8',
    )
    (tools / 'memory_recent_projection.py').write_text(
        "raise RuntimeError('feature branch helper loaded')\n", encoding='utf-8'
    )
    (tools / 'bootstrap_read_loop.py').write_bytes(
        (tools / 'bootstrap_read_loop.py').read_bytes() + b'\n# feature branch producer marker\n'
    )
    (tools / 'live_swarm.py').write_text(
        "raise RuntimeError('feature branch live_swarm loaded')\n", encoding='utf-8'
    )
    (tools / 'recurring_slot_registry.py').write_text(
        "raise RuntimeError('feature branch slot registry loaded')\n", encoding='utf-8'
    )
    subprocess.run(['git', 'add', 'tools'], cwd=alternate, check=True)
    subprocess.run(
        ['git', '-c', 'user.name=Bootstrap Test', '-c', 'user.email=bootstrap@example.invalid',
         'commit', '-q', '-m', 'feature head must not deploy'],
        cwd=alternate, check=True,
    )

    # The live runtime starts from an older but still self-healing producer, a helper
    # that would fail immediately if imported before repair, and a stale Atlas.
    producer_runtime = runtime / 'bootstrap_read_loop.py'
    producer_runtime.write_bytes(deployed_source['bootstrap_read_loop.py'] + b'\n# stale runtime producer marker\n')
    (runtime / 'memory_recent_projection.py').write_text(
        "raise RuntimeError('stale runtime helper loaded before self-heal')\n", encoding='utf-8'
    )
    atlas_runtime = runtime / 'stack_atlas.py'
    atlas_runtime.write_text(
        "import json\nprint(json.dumps({'schema':'bootstrap.v1','generated_at':'2026-09-11T11:00:00+00:00',"
        "'source_marker':'stale-runtime','memory_overview':{'recent':[]},"
        "'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    (runtime / 'live_swarm.py').write_text(
        "raise RuntimeError('stale runtime live_swarm loaded before self-heal')\n", encoding='utf-8'
    )
    (runtime / 'recurring_slot_registry.py').write_text(
        "raise RuntimeError('stale runtime slot registry loaded before self-heal')\n", encoding='utf-8'
    )

    # Dirty worktree bytes must not be promoted either.
    for name in ('bootstrap_read_loop.py', 'stack_atlas.py'):
        path = tools / name
        path.write_bytes(path.read_bytes() + b'\n# dirty working tree marker\n')
    (tools / 'memory_recent_projection.py').write_text(
        "raise RuntimeError('dirty worktree helper loaded')\n", encoding='utf-8'
    )

    _, overlay = _memory_files(alternate, tmp_path)
    env = os.environ.copy()
    env['VAULT_MEMORY_LOCAL_BANK'] = str(overlay)
    cp = subprocess.run(
        [
            sys.executable, str(producer_runtime), '--once', '--repo-root', str(alternate),
            '--atlas-path', str(atlas_runtime),
        ],
        cwd=str(alternate), capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=20, env=env,
    )

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    assert payload['source_marker'] == 'alternate-root'
    assert producer_runtime.read_bytes() == deployed_source['bootstrap_read_loop.py']
    assert (runtime / 'memory_recent_projection.py').read_bytes() == deployed_source['memory_recent_projection.py']
    assert atlas_runtime.read_bytes() == deployed_source['stack_atlas.py']
    assert (runtime / 'live_swarm.py').read_bytes() == deployed_source['live_swarm.py']
    assert (runtime / 'recurring_slot_registry.py').read_bytes() == deployed_source['recurring_slot_registry.py']
    assert b'feature branch producer marker' in (tools / 'bootstrap_read_loop.py').read_bytes()
    assert b'dirty working tree marker' in (tools / 'bootstrap_read_loop.py').read_bytes()


def test_once_overlays_fingerprint_current_recent_memory_projection(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    seed, overlay = _memory_files(alternate, tmp_path)
    recent = [
        {'id': f'mem-fresh-{index}', 'timestamp': f'2026-09-09T20:3{index}:00+03:00', 'title': f'fresh {index}', 'kind': 'lesson', 'scope': 'vault'}
        for index in range(5)
    ]
    write_recent_projection(seed_path=seed, overlay_path=overlay, recent=recent)

    cp = _run_once(alternate, overlay)

    assert cp.returncode == 0, cp.stderr
    assert cp.stdout == ''
    payload = json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8'))
    assert payload['memory_overview']['recent'] == recent[:3]
    source = payload['memory_overview']['recent_source']
    assert source['authority'] == 'DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION'
    assert source['read_mode'] == 'fingerprint_validated_recent_titles_projection'
    assert source['status'] == 'CURRENT_FOR_EFFECTIVE_MEMORY_FILES'
    assert source['generated_at']
    assert payload['memory_overview']['timeline_materialized'] == {
        'as_of': '2026-09-09T09:00:00+00:00',
        'read_mode': 'MATERIALIZED_ONLY',
    }


def test_once_rejects_projection_after_memory_source_changes(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    seed, overlay = _memory_files(alternate, tmp_path)
    write_recent_projection(
        seed_path=seed,
        overlay_path=overlay,
        recent=[{'id':'mem-fresh','timestamp':'2026-09-09T20:35:00+03:00','title':'fresh','kind':'lesson','scope':'vault'}],
    )
    overlay.write_text('{"changed":true}\n', encoding='utf-8')

    cp = _run_once(alternate, overlay)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8'))
    assert payload['memory_overview']['recent'] == [
        {'id':'materialized-old','timestamp':'2026-09-09T09:00:00+00:00','title':'materialized old'}
    ]
    assert 'recent_source' not in payload['memory_overview']


def test_once_missing_repo_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    overlay = tmp_path / 'local-memory' / 'memory-bank.local.jsonl'

    cp = _run_once(missing, overlay, quiet=False)

    assert cp.returncode == 1
    payload = json.loads(cp.stdout.lstrip("\ufeff"))
    assert payload["stream_schema"] == "bootstrap-read-stream.v1"
    assert payload["repo_root"] == str(missing.resolve())


def test_invalid_update_publishes_fresh_degraded_snapshot_and_watchdog_retries(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)
    good = _run_once(alternate, overlay)
    assert good.returncode == 0, good.stderr
    assert good.stdout == ''
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    previous = json.loads(destination.read_text(encoding='utf-8'))

    (alternate / 'tools' / 'stack_atlas.py').write_text("print('{}')", encoding='utf-8')
    degraded_run = _run_once(alternate, overlay)

    assert degraded_run.returncode == 0, degraded_run.stderr
    degraded = json.loads(destination.read_text(encoding='utf-8'))
    assert degraded['generated_at'] != previous['generated_at']
    assert degraded['bootstrap']['status'] == 'DEGRADED'
    assert degraded['bootstrap']['refresh_mode'] == 'DEGRADED_CARRY_FORWARD'
    assert degraded['bootstrap']['carried_forward_from'] == previous['generated_at']
    assert degraded['bootstrap']['agent_contract']['status'] == 'UNKNOWN'
    assert degraded['bootstrap_end'] == {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}
    status = json.loads((destination.parent / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'DEGRADED'

    marker = tmp_path / 'watchdog-retried.txt'
    (alternate / 'tools' / 'stack_atlas.py').write_text(
        "import json\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('retried')\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':datetime.now(timezone.utc).isoformat(),'bootstrap':{'status':'OK'},'memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    retry = _run_once(alternate, overlay, skip_if_fresh_seconds=45)
    assert retry.returncode == 0, retry.stderr
    assert marker.read_text(encoding='utf-8') == 'retried'
    repaired = json.loads(destination.read_text(encoding='utf-8'))
    assert repaired['bootstrap']['status'] == 'OK'


def test_replace_snapshot_retries_transient_windows_permission_error(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_retry_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    source = tmp_path / 'source.tmp'
    destination = tmp_path / 'latest.json'
    source.write_text('new', encoding='utf-8')
    destination.write_text('old', encoding='utf-8')
    real_replace = module.os.replace
    attempts = {'count': 0}

    def transient_replace(src, dst):
        attempts['count'] += 1
        if attempts['count'] <= 3:
            raise PermissionError('destination temporarily held open')
        return real_replace(src, dst)

    monkeypatch.setattr(module.os, 'name', 'nt')
    monkeypatch.setattr(module.os, 'replace', transient_replace)
    monkeypatch.setattr(module.time, 'sleep', lambda _seconds: None)
    module._replace_snapshot(source, destination, retry_seconds=0.5)

    assert attempts['count'] == 4
    assert destination.read_text(encoding='utf-8') == 'new'


def test_replace_snapshot_fails_closed_after_retry_deadline(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_retry_deadline_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    source = tmp_path / 'source.tmp'
    destination = tmp_path / 'latest.json'
    source.write_text('new', encoding='utf-8')
    destination.write_text('old', encoding='utf-8')
    monkeypatch.setattr(module.os, 'name', 'nt')
    monkeypatch.setattr(module.os, 'replace', lambda *_args: (_ for _ in ()).throw(PermissionError('locked')))

    with pytest.raises(PermissionError):
        module._replace_snapshot(source, destination, retry_seconds=0)
    assert source.exists()
    assert destination.read_text(encoding='utf-8') == 'old'


def test_glance_capture_does_not_wait_for_inherited_stdout_handles(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    _, overlay = _memory_files(alternate, tmp_path)
    (tools / 'stack_atlas.py').write_text(
        "import json, subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':'2026-09-11T03:00:00+00:00','memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}), flush=True)\n",
        encoding='utf-8',
    )

    started = __import__('time').monotonic()
    cp = _run_once(alternate, overlay)
    elapsed = __import__('time').monotonic() - started

    assert cp.returncode == 0, cp.stderr
    assert elapsed < 2.5
    payload = json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8'))
    assert payload['bootstrap_end']['status'] == 'COMPLETE'


def test_glance_timeout_is_bounded_without_pipe_eof_wait(tmp_path: Path) -> None:
    import importlib.util
    import time

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_timeout_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    atlas = tmp_path / 'stack_atlas.py'
    atlas.write_text('import time\ntime.sleep(30)\n', encoding='utf-8')

    started = time.monotonic()
    cp = module._run_bootstrap_glance(tmp_path, atlas, timeout_seconds=0.2)
    elapsed = time.monotonic() - started

    assert cp.returncode == 124
    assert 'timed out after 0.2s' in cp.stderr
    assert elapsed < 4.0


def test_persisted_budget_trims_recent_memory_overlay_before_stability_ceiling() -> None:
    recent = [
        {'id': f'mem-{i}', 'title': 'x' * 260, 'timestamp': '2026-09-13T09:00:00+00:00'}
        for i in range(3)
    ]
    payload = {
        'schema': 'bootstrap.v1',
        'bootstrap': {'status': 'OK', 'payload_budget': {
            'max_bytes': 2200,
            'stability_ceiling_bytes': 1500,
            'headroom_target_met': True,
        }},
        'fixed_summary': {'value': 's' * 500},
        'memory_overview': {
            'aggregate': {'eligible_entries': 500},
            'recent': recent,
            'recent_source': {'authority': 'DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION'},
        },
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }
    assert bootstrap_read_loop._serialized_snapshot_bytes(payload) > 1500

    fitted = bootstrap_read_loop._enforce_persisted_payload_budget(payload)

    assert bootstrap_read_loop._serialized_snapshot_bytes(fitted) <= 1500
    assert fitted['fixed_summary'] == payload['fixed_summary']
    assert fitted['memory_overview']['aggregate'] == {'eligible_entries': 500}
    assert len(fitted['memory_overview']['recent']) < 3
    source = fitted['memory_overview']['recent_source']
    assert source['budget_limited'] is True
    assert source['configured_limit'] == 3
    assert source['returned'] == len(fitted['memory_overview']['recent'])
    assert fitted['bootstrap']['payload_budget']['headroom_target_met'] is True


def test_persisted_budget_reports_unmet_headroom_when_recent_detail_is_exhausted() -> None:
    payload = {
        'schema': 'bootstrap.v1',
        'bootstrap': {'status': 'OK', 'payload_budget': {
            'max_bytes': 2500,
            'stability_ceiling_bytes': 1000,
            'headroom_target_met': True,
        }},
        'irreducible_summary': 'z' * 1400,
        'memory_overview': {
            'recent': [{'id': 'mem-1', 'title': 'y' * 300}],
            'recent_source': {'authority': 'DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION'},
        },
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }

    fitted = bootstrap_read_loop._enforce_persisted_payload_budget(payload)

    assert fitted['memory_overview']['recent'] == []
    assert fitted['memory_overview']['recent_source']['budget_limited'] is True
    assert fitted['bootstrap']['payload_budget']['headroom_target_met'] is False
    assert bootstrap_read_loop._serialized_snapshot_bytes(fitted) <= 2500
    assert fitted['irreducible_summary'] == payload['irreducible_summary']


def test_persisted_budget_blocks_hard_cap_after_overlay() -> None:
    payload = {
        'schema': 'bootstrap.v1',
        'bootstrap': {'status': 'OK', 'payload_budget': {
            'max_bytes': 1200,
            'stability_ceiling_bytes': 1000,
        }},
        'irreducible_summary': 'z' * 1600,
        'memory_overview': {'recent': []},
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }

    with pytest.raises(RuntimeError, match='exceeds advertised payload max'):
        bootstrap_read_loop._enforce_persisted_payload_budget(payload)


def test_producer_status_computes_unmet_headroom_from_persisted_bytes(tmp_path: Path) -> None:
    destination = tmp_path / '.state' / 'bootstrap' / 'latest.json'
    payload = {
        'schema': 'bootstrap.v1',
        'generated_at': '2026-09-13T09:00:00+00:00',
        'bootstrap': {'status': 'OK', 'payload_budget': {
            'max_bytes': 25000,
            'headroom_reserve_bytes': 4000,
            'stability_ceiling_bytes': 21000,
            'headroom_target_met': True,
        }},
        'synthetic_irreducible': 'x' * 22000,
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')

    observation = bootstrap_read_loop._snapshot_budget_observation(tmp_path)

    assert observation['available'] is True
    assert observation['bytes'] == len(destination.read_bytes())
    assert observation['bytes'] > observation['stability_ceiling_bytes']
    assert observation['headroom_target_met'] is False
    assert observation['headroom_bytes'] == 25000 - observation['bytes']


def test_full_producer_status_exposes_persisted_payload_headroom(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    (tools / 'stack_atlas.py').write_text(
        "import json; from datetime import datetime, timezone; "
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':datetime.now(timezone.utc).isoformat(),"
        "'bootstrap':{'status':'OK','payload_budget':{'max_bytes':25000,'compaction_target_bytes':15000,"
        "'headroom_reserve_bytes':4000,'stability_ceiling_bytes':21000,'compacted':True,'headroom_compacted':True}},"
        "'memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)

    cp = _run_once(alternate, overlay)

    assert cp.returncode == 0, cp.stderr
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    persisted = destination.read_bytes()
    status_path = destination.parent / 'producer-status.json'
    status = json.loads(status_path.read_text(encoding='utf-8'))
    observation = status['snapshot']
    assert status['mode'] == 'FULL'
    assert observation['available'] is True
    assert observation['bytes'] == len(persisted)
    assert observation['bootstrap_end_status'] == 'COMPLETE'
    assert observation['max_bytes'] == 25000
    assert observation['stability_ceiling_bytes'] == 21000
    assert observation['headroom_reserve_bytes'] == 4000
    assert observation['headroom_bytes'] == 25000 - len(persisted)
    assert observation['headroom_target_met'] is True
    assert observation['headroom_compacted'] is True
    assert len(status_path.read_bytes()) < 2048


def test_skip_if_fresh_avoids_bootstrap_glance(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = {
        'schema': 'bootstrap.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'bootstrap': {'status': 'OK', 'payload_budget': {
            'max_bytes': 25000, 'compaction_target_bytes': 15000,
            'headroom_reserve_bytes': 4000, 'stability_ceiling_bytes': 21000,
            'compacted': True, 'headroom_compacted': False,
        }},
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }
    destination.write_text(json.dumps(original), encoding='utf-8')

    cp = _run_once(alternate, overlay, skip_if_fresh_seconds=45)

    assert cp.returncode == 0, cp.stderr
    assert not marker.exists()
    assert json.loads(destination.read_text(encoding='utf-8')) == original
    status = json.loads((destination.parent / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'SKIPPED_FRESH'
    observation = status['snapshot']
    assert observation['bytes'] == len(destination.read_bytes())
    assert observation['headroom_bytes'] == 25000 - len(destination.read_bytes())
    assert observation['headroom_target_met'] is True


def test_skip_if_fresh_refreshes_stale_snapshot(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        "import json\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('ran')\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':datetime.now(timezone.utc).isoformat(),'memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        'schema': 'bootstrap.v1',
        'generated_at': (datetime.now(timezone.utc) - timedelta(seconds=70)).isoformat(),
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }), encoding='utf-8')

    cp = _run_once(alternate, overlay, skip_if_fresh_seconds=45)

    assert cp.returncode == 0, cp.stderr
    assert marker.read_text(encoding='utf-8') == 'ran'
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['bootstrap_end']['status'] == 'COMPLETE'
    generated = datetime.fromisoformat(payload['generated_at'])
    assert (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() < 5


def test_skip_if_fresh_refreshes_invalid_snapshot(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('{"schema":"bootstrap.v1"}', encoding='utf-8')

    cp = _run_once(alternate, overlay, skip_if_fresh_seconds=45)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['source_marker'] == 'alternate-root'
    assert payload['bootstrap_end']['status'] == 'COMPLETE'


def test_default_glance_timeout_allows_loaded_but_bounded_refresh() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_timeout_constant_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.BOOTSTRAP_GLANCE_TIMEOUT_SECONDS == 30.0


def test_singleflight_skips_second_producer_while_lock_is_held(tmp_path: Path) -> None:
    import importlib.util
    import time

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_lock_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    lock = module._try_acquire_producer_lock(alternate)
    assert lock is not None
    try:
        started = time.monotonic()
        cp = _run_once(alternate, overlay)
        elapsed = time.monotonic() - started
    finally:
        module._release_producer_lock(lock)
    assert cp.returncode == 0, cp.stderr
    assert elapsed < 2.0
    assert not marker.exists()
    status = json.loads((alternate / '.state' / 'bootstrap' / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'SKIPPED_INFLIGHT'


def _write_complete_snapshot(destination: Path, *, age_seconds: float, status: str = 'OK') -> dict:
    from datetime import datetime, timedelta, timezone
    payload = {
        'schema': 'bootstrap.v1',
        'generated_at': (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat(),
        'bootstrap': {'status': status, 'agent_contract': {'status': 'COHERENT'}},
        'live_swarm': {'available': True, 'status': 'LIVE'},
        'github': {'available': True, 'status': 'OK'},
        'swarm_topology': {'recurring_workers_total': 10},
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload), encoding='utf-8')
    return payload


def test_watchdog_heartbeat_refreshes_stale_snapshot_without_running_atlas(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    previous = _write_complete_snapshot(destination, age_seconds=70)

    cp = _run_once(alternate, overlay, heartbeat_if_older_than_seconds=45)

    assert cp.returncode == 0, cp.stderr
    assert not marker.exists()
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['generated_at'] != previous['generated_at']
    assert payload['bootstrap']['status'] == 'DEGRADED'
    assert payload['bootstrap']['refresh_mode'] == 'WATCHDOG_HEARTBEAT'
    assert payload['bootstrap']['carried_forward_from'] == previous['generated_at']
    assert payload['bootstrap']['agent_contract']['status'] == 'UNKNOWN'
    assert payload['live_swarm']['status'] == 'UNKNOWN'
    assert payload['github']['status'] == 'UNKNOWN'
    assert payload['swarm_topology']['status'] == 'UNKNOWN'
    assert payload['bootstrap_end'] == {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}
    status = json.loads((destination.parent / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'WATCHDOG_HEARTBEAT'


def test_watchdog_heartbeat_skips_fresh_complete_snapshot_without_running_atlas(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    original = _write_complete_snapshot(destination, age_seconds=5)

    cp = _run_once(alternate, overlay, heartbeat_if_older_than_seconds=45)

    assert cp.returncode == 0, cp.stderr
    assert not marker.exists()
    assert json.loads(destination.read_text(encoding='utf-8')) == original
    status = json.loads((destination.parent / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'WATCHDOG_SKIPPED_FRESH'


def test_watchdog_heartbeat_bypasses_stuck_primary_lock_without_running_atlas(tmp_path: Path) -> None:
    import importlib.util
    import time

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    _write_complete_snapshot(destination, age_seconds=70)
    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_heartbeat_lock_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    producer_lock = module._try_acquire_producer_lock(alternate)
    assert producer_lock is not None
    try:
        started = time.monotonic()
        cp = _run_once(alternate, overlay, heartbeat_if_older_than_seconds=45)
        elapsed = time.monotonic() - started
    finally:
        module._release_producer_lock(producer_lock)

    assert cp.returncode == 0, cp.stderr
    assert elapsed < 2.0
    assert not marker.exists()
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['bootstrap']['refresh_mode'] == 'WATCHDOG_HEARTBEAT'
    assert payload['bootstrap']['status'] == 'DEGRADED'


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object behavior')
def test_windows_job_object_kills_atlas_child_when_producer_is_killed(tmp_path: Path) -> None:
    import time

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    _, overlay = _memory_files(alternate, tmp_path)
    child_pid_file = tmp_path / 'atlas-child.pid'
    (tools / 'stack_atlas.py').write_text(
        "import os, time\n"
        "from pathlib import Path\n"
        f"Path(r'{child_pid_file}').write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(30)\n",
        encoding='utf-8',
    )
    env = os.environ.copy()
    env['VAULT_MEMORY_LOCAL_BANK'] = str(overlay)
    producer = subprocess.Popen(
        [sys.executable, str(SCRIPT), '--once', '--quiet', '--repo-root', str(alternate)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and not child_pid_file.exists():
        time.sleep(0.02)
    assert child_pid_file.exists(), 'Atlas child did not start'
    child_pid = int(child_pid_file.read_text(encoding='utf-8'))

    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def pid_exists(pid: int) -> bool:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True

    assert pid_exists(child_pid)
    producer.kill()
    producer.wait(timeout=5)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and pid_exists(child_pid):
        time.sleep(0.02)
    if pid_exists(child_pid):
        subprocess.run(['taskkill.exe', '/PID', str(child_pid), '/T', '/F'], capture_output=True)
        pytest.fail(f'Atlas child {child_pid} survived producer termination')


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object behavior')
def test_windows_job_assignment_failure_fails_closed_without_unmanaged_child(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_job_failure_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    atlas = tmp_path / 'stack_atlas.py'
    atlas.write_text('import time\ntime.sleep(30)\n', encoding='utf-8')
    monkeypatch.setattr(
        module,
        '_assign_windows_kill_on_close_job',
        lambda _process: (_ for _ in ()).throw(OSError(5, 'assignment denied')),
    )
    cp = module._run_bootstrap_glance(tmp_path, atlas, timeout_seconds=5)
    assert cp.returncode == module.WINDOWS_JOB_OBJECT_ASSIGN_FAILURE_EXIT_CODE
    assert 'job assignment failed' in cp.stderr



def test_resource_pressure_thresholds_are_conservative() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_pressure_threshold_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    gib = 1024 ** 3
    assert module._resource_pressure_from_memory_values(
        available_physical=2 * gib,
        commit_limit=64 * gib,
        commit_available=20 * gib,
    ) is None
    low_phys_only = module._resource_pressure_from_memory_values(
        available_physical=512 * 1024 ** 2,
        commit_limit=64 * gib,
        commit_available=20 * gib,
    )
    assert low_phys_only is None
    high_commit_only = module._resource_pressure_from_memory_values(
        available_physical=2 * gib,
        commit_limit=64 * gib,
        commit_available=8 * gib,
    )
    assert high_commit_only is None
    combined = module._resource_pressure_from_memory_values(
        available_physical=512 * 1024 ** 2,
        commit_limit=64 * gib,
        commit_available=8 * gib,
    )
    assert combined is not None
    assert combined['reasons'] == ['low_free_physical_memory', 'high_commit_pressure']


def test_singleflight_load_sheds_without_running_atlas_when_snapshot_exists(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_load_shed_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    destination = tmp_path / '.state' / 'bootstrap' / 'latest.json'
    previous = _write_complete_snapshot(destination, age_seconds=5)
    marker = tmp_path / 'atlas-ran.txt'
    atlas = tmp_path / 'atlas.py'
    atlas.write_text(f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n", encoding='utf-8')
    pressure = {
        'status': 'SEVERE',
        'reasons': ['low_free_physical_memory', 'high_commit_pressure'],
        'available_physical_mb': 400.0,
        'commit_used_pct': 90.0,
    }
    monkeypatch.setattr(module, '_windows_resource_pressure', lambda: pressure)

    assert module._emit_singleflight(tmp_path, quiet=True, atlas_path=atlas)
    assert not marker.exists()
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['generated_at'] != previous['generated_at']
    assert payload['bootstrap']['status'] == 'DEGRADED'
    assert payload['bootstrap']['refresh_mode'] == 'RESOURCE_PRESSURE_SHED'
    assert payload['bootstrap']['resource_pressure'] == pressure
    assert payload['live_swarm']['status'] == 'UNKNOWN'
    assert payload['bootstrap_end']['status'] == 'COMPLETE'
    status = json.loads((destination.parent / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'RESOURCE_PRESSURE_SHED'


def test_first_materialization_still_attempts_full_refresh_under_pressure(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_first_pressure_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        '_windows_resource_pressure',
        lambda: {'status': 'SEVERE', 'reasons': ['low_free_physical_memory', 'high_commit_pressure']},
    )
    called = []
    monkeypatch.setattr(module, 'emit_snapshot', lambda *args, **kwargs: called.append(True) or True)
    assert module._emit_singleflight(tmp_path, quiet=True)
    assert called == [True]
