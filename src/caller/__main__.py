"""CLI entry point.

    python -m caller serve                 run the webhook/websocket server
    python -m caller call <scenario>       place one test call end to end
    python -m caller campaign <ids...>     run several scenarios back to back
    python -m caller list                  scenarios + completed calls
    python -m caller analyze               mine transcripts for bugs (see analyze/)
    python -m caller dashboard             mission control UI over calls/

`call` and `campaign` start the server in-process if one isn't already
listening, so after setup a single command runs a whole test call.
"""

from __future__ import annotations

import argparse
import sys
import time

from caller import store
from caller.config import ConfigError, load_config
from caller.scenario import ScenarioError, list_scenarios, load_scenario


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from caller.server import create_app

    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info")
    return 0


def _ensure_server(cfg) -> None:
    from caller import orchestrate

    if not orchestrate.server_is_up(cfg):
        print(f"starting server on port {cfg.port}...")
        orchestrate.start_server_thread(cfg)


def _cmd_call(args: argparse.Namespace) -> int:
    from caller import orchestrate

    cfg = load_config()
    load_scenario(args.scenario)  # validate before spending telephony money
    _ensure_server(cfg)
    call_dir = orchestrate.run_scenario(cfg, args.scenario)
    return 0 if call_dir else 1


def _cmd_campaign(args: argparse.Namespace) -> int:
    from caller import orchestrate

    cfg = load_config()
    ids = list_scenarios() if args.all else args.scenarios
    if not ids:
        print("no scenarios given (pass ids or --all)", file=sys.stderr)
        return 2
    for sid in ids:
        load_scenario(sid)  # validate the whole batch up front
    _ensure_server(cfg)

    failures = 0
    for i, sid in enumerate(ids):
        print(f"\n[{i + 1}/{len(ids)}] {sid}")
        if orchestrate.run_scenario(cfg, sid) is None:
            failures += 1
        if i + 1 < len(ids):
            time.sleep(args.gap)
    print(f"\ncampaign done: {len(ids) - failures}/{len(ids)} calls produced artifacts")
    return 0 if failures == 0 else 1


def _cmd_list(args: argparse.Namespace) -> int:
    print("scenarios:")
    for sid in list_scenarios():
        try:
            s = load_scenario(sid)
            print(f"  {sid:24s} [{s.category}/{s.behavior}] {s.title}")
        except ScenarioError as e:
            print(f"  {sid:24s} (unloadable: {e})")
    calls = store.list_calls()
    print(f"\ncompleted calls: {len(calls)}")
    for call_dir in calls:
        data = store.load_call(call_dir)
        meta = data.get("meta") or {}
        tel = data.get("telemetry") or {}
        rec = "rec" if data.get("recording") else "NO REC"
        ended = meta.get("ended_by", "?")
        print(
            f"  {call_dir.name:28s} {tel.get('call_duration_secs', '?'):>6}s "
            f"{tel.get('completed_turns', '?'):>2} turns  [{rec}]  ended: {ended}"
        )
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from caller.analyze.judge import analyze_calls
    from caller.analyze.report import render_bug_report

    cfg = load_config()
    findings = analyze_calls(cfg, force=args.force)
    path = render_bug_report(findings)
    print(f"bug report written to {path}")
    return 0


def _cmd_knowledge(args: argparse.Namespace) -> int:
    from caller import knowledge

    k = knowledge.load()
    print(f"practice facts ({len(k['practice_facts'])}):")
    for f in k["practice_facts"]:
        print(f"  - {f['text']}  [{f['source']}]")
    print(f"leads ({len(k['leads'])}):")
    for f in k["leads"]:
        print(f"  - {f['text']}  [{f['source']}]")
    return 0


def _cmd_latency(args: argparse.Namespace) -> int:
    from caller.analyze.latency import collect, render

    path = render(collect())
    print(path.read_text())
    print(f"written to {path}")
    return 0


def _cmd_hunt(args: argparse.Namespace) -> int:
    import anthropic

    from caller import knowledge, orchestrate
    from caller.hunt import generate_hunt

    cfg = load_config()
    hunt_id = generate_hunt(
        anthropic.Anthropic(api_key=cfg.anthropic_api_key), cfg.judge_model, knowledge.load()
    )
    s = load_scenario(hunt_id)
    print(f"generated scenarios/{hunt_id}.yaml: {s.title}")
    if args.no_call:
        return 0
    _ensure_server(cfg)
    return 0 if orchestrate.run_scenario(cfg, hunt_id) else 1


def _cmd_dashboard(args: argparse.Namespace) -> int:
    import uvicorn

    from caller.dashboard import create_dashboard_app

    print(f"mission control: http://localhost:{args.port}")
    uvicorn.run(create_dashboard_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caller", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="run the webhook/websocket server").set_defaults(fn=_cmd_serve)

    p_call = sub.add_parser("call", help="place one test call")
    p_call.add_argument("scenario", help="scenario id (see `list`)")
    p_call.set_defaults(fn=_cmd_call)

    p_camp = sub.add_parser("campaign", help="run several scenarios back to back")
    p_camp.add_argument("scenarios", nargs="*", help="scenario ids")
    p_camp.add_argument("--all", action="store_true", help="run every scenario")
    p_camp.add_argument("--gap", type=float, default=10.0, help="seconds between calls")
    p_camp.set_defaults(fn=_cmd_campaign)

    sub.add_parser("list", help="list scenarios and completed calls").set_defaults(fn=_cmd_list)

    sub.add_parser(
        "knowledge", help="show the campaign's cross-call memory"
    ).set_defaults(fn=_cmd_knowledge)

    sub.add_parser(
        "latency", help="render the cross-call latency report"
    ).set_defaults(fn=_cmd_latency)

    p_hunt = sub.add_parser("hunt", help="author a scenario from the open leads and run it")
    p_hunt.add_argument("--no-call", action="store_true", help="generate the YAML only")
    p_hunt.set_defaults(fn=_cmd_hunt)

    p_dash = sub.add_parser("dashboard", help="serve the mission-control UI")
    p_dash.add_argument("--port", type=int, default=8090)
    p_dash.set_defaults(fn=_cmd_dashboard)

    p_an = sub.add_parser("analyze", help="mine call artifacts for bugs")
    p_an.add_argument("--force", action="store_true", help="re-analyze calls already judged")
    p_an.set_defaults(fn=_cmd_analyze)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (ConfigError, ScenarioError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
