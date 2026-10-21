"""Manual opt-in acquisition, never invokes a consumer repository."""
import argparse
import json
from pathlib import Path

from .http_collection import Collector, validate_manifest
from .primitives import ContractError
from .stage import StageLedger


def source_from_plan(file: str, source_id: str):
    value=json.loads(Path(file).read_text(encoding='utf-8-sig'))
    if (not isinstance(value,dict) or value.get('format')!='ssr.source-plan.v1'
            or not isinstance(value.get('sources'),list)):
        raise ContractError('expected central ssr.source-plan.v1; no policy inferred from a URL')
    matches=[s for s in value['sources'] if s.get('source_id')==source_id]
    if len(matches)!=1: raise ContractError('source-id must resolve to one central source record')
    return matches[0]


def main() -> None:
    parser=argparse.ArgumentParser(prog='ssr-collector-peak')
    commands=parser.add_subparsers(dest='action',required=True)
    collect=commands.add_parser('http-collect',help='OPTIONAL HTTP architecture, not the user-selected Chrome acquisition route; dry-run by default')
    collect.add_argument('--plan',required=True); collect.add_argument('--source-id',required=True)
    collect.add_argument('--stage-dir'); collect.add_argument('--fetch',action='store_true')
    intake=commands.add_parser('intake-file',help='stage an already permitted local file; does not collect a website or claim a Chrome export')
    intake.add_argument('--plan',required=True); intake.add_argument('--source-id',required=True)
    intake.add_argument('--file',required=True); intake.add_argument('--stage-dir',required=True)
    intake.add_argument('--format',choices=['plain_text','html'],required=True)
    intake.add_argument('--origin',choices=['operator_file','synthetic_fixture'],required=True)
    intake.add_argument('--capture-receipt',help='optional ssr.browser-export.v1 observation file; requires operator_file HTML')
    bundle=commands.add_parser('bundle',help='write a private data-only packet; does not invoke the archive')
    bundle.add_argument('--stage-dir',required=True); bundle.add_argument('--snapshot-id',required=True); bundle.add_argument('--output-dir',required=True)
    stats=commands.add_parser('stats'); stats.add_argument('--stage-dir',required=True)
    args=parser.parse_args()
    try:
        if args.action=='http-collect':
            source=source_from_plan(args.plan,args.source_id)
            if not args.fetch:
                result={'mode':'optional_http_dry_run','selected_route':'computer_use_or_permitted_file','source_id':source['source_id'],'url':source['url'],'allow_fetch':source['policy']['allow_fetch'],
                    'purpose_states':{k:v['status'] for k,v in source['policy']['uses'].items()},'network_requests':0,'stage_created':False}
            else:
                if not args.stage_dir: raise ContractError('--fetch requires a private --stage-dir')
                if source.get('acquisition'): raise ContractError('import sources cannot become HTTP sources')
                sources=validate_manifest({'manifest_version':1,'game':'PEAK:3527290','sources':[source]})
                with StageLedger(args.stage_dir) as stage: result=Collector(stage).collect(sources)[0]
        elif args.action=='intake-file':
            from .file_intake import intake_file
            source=source_from_plan(args.plan,args.source_id)
            with StageLedger(args.stage_dir) as stage:
                receipt=json.loads(Path(args.capture_receipt).read_text(encoding='utf-8-sig')) if args.capture_receipt else None
                result=intake_file(stage,source,args.file,args.format,args.origin,receipt)
        else:
            with StageLedger(args.stage_dir) as stage:
                result=stage.bundle(args.snapshot_id,args.output_dir) if args.action=='bundle' else stage.stats()
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result.get('state')=='blocked_or_failed': raise SystemExit(2)
    except (ContractError,OSError,ValueError) as exc:
        print(json.dumps({'status':'error','error':str(exc)},ensure_ascii=False)); raise SystemExit(1) from exc
