"""Command line entry point shared by Bash wrappers and the interactive menu."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from .common import ROOT, read_json, atomic_bytes
from .audit import Audit
from .engine import project_lock, stage, apply, rollback, backup_bundle, check_bundle, import_bundle, transaction_path
from .snapshot import capture
from .plan import make_plan, source_guard, host_fingerprint, require_destination_host, load_plan
from .validation import validate, compare, doctor


def confirmation(phrase):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('Live changes require an interactive terminal and explicit confirmation')
    print('Esta operación modifica el destino. Revisa el plan y sus acciones pendientes.')
    if input('Escribe '+phrase+' para continuar: ').strip()!=phrase:
        raise ValueError('Operation cancelled; no deployment performed')


def print_plan(plan):
    print('MYARCH — Plan '+plan['id'][:12])
    print('Perfiles: '+', '.join(plan['profiles']))
    print('Equipo origen protegido: '+str(plan['target_is_source']))
    print('GPU destino: '+', '.join(plan['hardware']['target']['gpu']))
    for a in plan['actions']:
        print(f"{a['status']:24} {a['kind']:7} {a.get('name',a.get('path'))}" + (': '+a['reason'] if a.get('reason') else ''))
    print('Estados: '+json.dumps(dict(Counter(a['status'] for a in plan['actions'])),ensure_ascii=False))
    for text in plan['manual']+plan['warnings']:
        print('• '+text)
    print('Plan guardado: '+str(ROOT/'state/plans'/f"{plan['id']}.json"))


def report():
    audit=read_json(ROOT/'manifests/audit-report.json')
    pkgs=read_json(ROOT/'manifests/packages.json')
    dot=read_json(ROOT/'manifests/dotfiles.json')
    hardware=read_json(ROOT/'manifests/hardware.json')
    lines=['# Auditoría local MyArch','',f"Fecha UTC: {audit['generated_at']}",'',
           'Inventario observado; no es una promesa de restauración completa. Este informe permanece excluido de Git.', '',
           '## Cobertura','', '```json',json.dumps(audit['summary'],indent=2),'```','',
           '## Hardware','',*[f"- {x['device']} / {x['driver']}" for x in hardware['gpu']], '',
           'Los monitores físicos y HEADLESS se registran como datos de origen y necesitan revisión en destino.', '',
           '## Configuración visual','',
           *[f"- `{e['source']}` — {e['status']}; {e.get('restore')}" for e in dot['entries']], '',
           '## Paquetes extranjeros','',
           *[f"- {p['name']} {p['version']} — {p['origin']}; {len(p.get('source_evidence',[]))} árbol(es) local(es)." for p in pkgs['packages'] if p['origin'].startswith('foreign')], '',
           'Un árbol AUR local no demuestra que el binario instalado se construyera con esa receta.', '',
           '## Dependencias y recursos pendientes','',
           *[f"- `{e['from']}` → `{e['expression']}`: {e['status']}" for e in dot['include_graph']], '',
           *[f"- `{e.get('source')}`: {e.get('redistribution','manual_review')}" for e in dot['visual_resources']], '',
           '## Límites','',*['- '+x for x in dot['limitations']], '',
           'SDDM: selección y metadatos; no se activa el tema ni se copia su árbol sin revisión de licencia.',
           'No se han ejecutado aplicaciones gráficas, configs Lua/Fish, herramientas ofensivas ni comandos privilegiados.',
           'Las consultas fallidas o ausentes figuran en manifests/audit-report.json; una ausencia no equivale a inventario vacío confirmado.','']
    path=ROOT/'reports/AUDIT.md'
    atomic_bytes(path,'\n'.join(lines).encode())
    return {'report':str(path)}


def main():
    parser=argparse.ArgumentParser(description='MyArch — Personal Arch Linux Environment. Default actions are read-only or confined to MyArch.')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ['audit','capture','doctor','report','profiles']:
        sub.add_parser(name)
    p=sub.add_parser('plan'); p.add_argument('--profile',action='append',default=[]); p.add_argument('--snapshot',default='latest');p.add_argument('--json',action='store_true')
    p=sub.add_parser('stage');p.add_argument('--snapshot',default='latest');p.add_argument('--dest',type=Path);p.add_argument('--portable-only',action='store_true')
    p=sub.add_parser('apply');p.add_argument('--plan',default='latest');p.add_argument('--resume')
    for name in ['validate','compare','backup']:
        p=sub.add_parser(name);p.add_argument('--snapshot',default='latest')
        if name=='validate':p.add_argument('--plan')
    p=sub.add_parser('rollback');p.add_argument('transaction')
    for name in ['bundle-check','bundle-import']:
        p=sub.add_parser(name);p.add_argument('directory',type=Path)
    args=parser.parse_args()
    with project_lock():
        if args.command=='audit':
            guard=source_guard()
            if guard['machine_hash']!=host_fingerprint():
                raise ValueError('This checkout contains another source computer; audit the destination in a separate checkout')
            result=Audit().execute()
            report()
        elif args.command=='capture':result=capture()
        elif args.command=='profiles':
            result={p.stem:read_json(p)['description'] for p in sorted((ROOT/'config/profiles').glob('*.json'))}
        elif args.command=='plan':
            names=[p for raw in (args.profile or ['full']) for p in raw.split(',')]
            result=make_plan(names,args.snapshot)
            if not args.json:
                print_plan(result)
                return 0
        elif args.command=='stage':result=stage(args.snapshot,args.dest,args.portable_only)
        elif args.command=='apply':
            require_destination_host()
            p=load_plan(args.plan)
            print_plan(p)
            confirmation('APLICAR '+p['id'][:12])
            result=apply(p['id'],args.resume)
            validation=validate(p['capture'],p['id'])
            result['validation']=validation
        elif args.command=='rollback':
            tx=read_json(transaction_path(args.transaction))
            if tx['kind']=='apply':
                require_destination_host()
                confirmation('RESTAURAR '+args.transaction)
            result=rollback(args.transaction)
        elif args.command=='backup':result=backup_bundle(args.snapshot)
        elif args.command=='bundle-check':result=check_bundle(args.directory)
        elif args.command=='bundle-import':result=import_bundle(args.directory)
        elif args.command=='validate':result=validate(args.snapshot,args.plan)
        elif args.command=='compare':
            full=compare(args.snapshot)
            result={'report':str(ROOT/'reports/compare.json'),
                    'files':dict(Counter(e['status'] for e in full['files'])),
                    'packages':dict(Counter(e['status'] for e in full['packages']))}
        elif args.command=='doctor':result=doctor()
        elif args.command=='report':result=report()
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if args.command=='validate' and (not result['integrity_ok'] or result['deployment_ok'] is False):
            return 1
        if args.command=='bundle-check' and not result['valid']:
            return 1
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print('MyArch: '+str(exc),file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print('\nMyArch: interrupted. Check state/transactions before resuming.',file=sys.stderr)
        sys.exit(130)
