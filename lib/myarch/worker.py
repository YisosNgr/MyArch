"""Read-only authorization immediately before the Bash package worker uses sudo."""
import os
import sys
from .common import ROOT, HOME, CONFIG, read_json, run
from .plan import require_destination_host, load_plan, host_fingerprint


def authorize(targets):
    require_destination_host()
    plan=load_plan(os.environ.get('MYARCH_APPROVED_PLAN',''))
    if (plan['target_host']!=host_fingerprint() or plan['target_home']!=str(HOME)
            or plan['target_config']!=str(CONFIG)):
        raise ValueError('Package plan belongs to a different destination')
    allowed={a.get('target') for a in plan['actions']
             if a['kind']=='package' and a['status']=='Pending'}
    if not targets or any(t not in allowed for t in targets):
        raise ValueError('Package worker targets differ from the reviewed plan')
    trusted=read_json(ROOT/'config/policy.json')['trusted_repositories']
    configured=run(['pacman-conf','--repo-list'])
    if (configured['status']!='ok' or any(r not in trusted for r in configured['stdout'].splitlines())
            or any(t.partition('/')[0] not in trusted for t in targets)):
        raise ValueError('Package worker requires reviewed target repositories')


if __name__=='__main__':
    try:
        authorize(sys.argv[1:])
    except (ValueError,OSError,KeyError) as exc:
        print('MyArch: '+str(exc),file=sys.stderr)
        sys.exit(2)
