"""Preregistered maximum-green experiment on paired recorded demand. No model API calls.

Writes isolated run evidence; never changes the active UI policy or its data.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

import pandas as pd
from trafik.aday import evaluate_candidate
from trafik.akis import talep_sayimlari
from trafik.degerlendir import ISINMA_S, SURE_S, _tek_kosu, denetle
from trafik.sonuclar import ozetle, talep_yolu, trip_oku
from trafik.sprint import sha256
from trafik.sumo_ag import faz_plani_surelerden, kur
from trafik import uyarlamali


def write(path, data):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(path)


def input_hashes():
    names = ['data/gelisler.parquet', 'data/akis_izler.parquet', 'data/geometri.json',
             'data/sinyal_plani.json', 'data/sim_kalibrasyon.json', 'web/veri/ozet.json',
             'config/sprint.json', 'scripts/sprint_adaptive.py']
    paths = [ROOT/p for p in names] + list((ROOT/'src/trafik').glob('*.py'))
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def pedestrian_guard(candidate, baseline):
    checks = []
    base = {r['tohum']: r['yaya_hizmeti'] for r in baseline['denetleyici_kaydi']}
    for run in candidate['denetleyici_kaydi']:
        seed, audit = run['tohum'], run['yaya_hizmeti']
        for phase in uyarlamali.YAYA_SURE:
            a = base[seed]['azami_hizmetsiz_bosluk_s'][phase]
            b = audit['azami_hizmetsiz_bosluk_s'][phase]
            checks.append({'seed': seed, 'phase': phase, 'baseline_max_no_service_gap_s': a,
                           'candidate_max_no_service_gap_s': b, 'passed': b <= a})
    return {'passed': all(c['passed'] for c in checks), 'checks': checks,
            'scope': 'Additional no-regression guard against the same adaptive rule at 60 s. '
                     'Continuous green after the required crossing duration counts as available service. '
                     'These are assumed requests, not pedestrian trajectories or a 120 s deadline guarantee.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', type=int, default=[1, 2, 3])
    args = parser.parse_args()
    if not args.seeds or len(set(args.seeds)) != len(args.seeds):
        parser.error('Use unique paired seeds')
    protocol = json.loads((ROOT/'config/sprint.json').read_text(encoding='utf-8'))
    ui = json.loads((ROOT/'web/veri/ozet.json').read_text(encoding='utf-8'))
    drivers = {k: ui['kalibrasyon']['en_iyi'][k] for k in ('tau', 'accel')}
    counts = talep_sayimlari(pd.read_parquet(ROOT/'data/akis_izler.parquet'))
    output = ROOT/'data/sprint'/('adaptive-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    hashes = input_hashes()
    candidates = [{'name': f'{rule}_{maximum}', 'rule': rule, 'parameters': {'max_green_s': maximum}}
                  for rule in ('saf', 'agirlikli') for maximum in (30, 45, 60)]
    registration = {'registered_at_utc': datetime.now(timezone.utc).isoformat(), 'seeds': args.seeds,
                    'candidates': candidates, 'gates': protocol['candidate_gates'], 'input_hashes': hashes,
                    'additional_guards': ['No insertion-aware total-loss regression',
                        'Apply configured global p95 limit to every approach',
                        'No pedestrian max no-service-gap regression against same rule at max_green=60'],
                    'selection': 'Keep active fixed plan; no automatic policy promotion. A candidate must pass '
                        'all vehicle gates against both current and selected fixed plans, plus pedestrian guard.',
                    'scope': 'Retrospective development on existing video; seeds vary drivers, not independent mornings.'}
    write(output/'preregistration.json', registration)
    print('Registered '+str(output), flush=True)
    results, demands = {}, {}
    for name, plan in (('current', ui['mevcut_plan']), ('agent_recorded', ui['ajan']['cevap']['recommended_plan'])):
        if denetle(plan):
            raise ValueError('Invalid baseline plan')
        cfg = kur(output/name, counts, SURE_S, {}, 0, surucu=drivers, gelis='gercek',
                  fazlar=faz_plani_surelerden(*(plan[k] for k in ('sol_onde', 'guney_onde', 'ortak', 'ara_sokak'))))
        demands[name] = {str(s): sha256(talep_yolu(cfg)) for s in args.seeds}
        frames = [_tek_kosu(cfg, s).assign(tohum=s) for s in args.seeds]
        results[name] = {'gecerli': True, 'plan': plan, **ozetle(pd.concat(frames), tuple(args.seeds))}
        write(output/(name+'.json'), results[name])
        print(name+': '+str(results[name]['ort_toplam_kayip_s'])+' s total', flush=True)
    for candidate in candidates:
        name, rule, parameters = candidate['name'], candidate['rule'], candidate['parameters']
        cfg = uyarlamali.hazirla(counts, drivers, 'gercek', str(output/name))
        demands[name] = {str(s): sha256(talep_yolu(cfg)) for s in args.seeds}
        frames, audit = [], []
        for seed in args.seeds:
            run = uyarlamali.calistir(cfg, rule, seed, parametreler=parameters)
            frames.append(trip_oku(run['trip'], talep_yolu(cfg), ISINMA_S).assign(tohum=seed))
            audit.append({'tohum': seed, 'kararlar': run['kararlar'], 'yaya_hizmeti': run['yaya_hizmeti']})
            print(name+' seed '+str(seed)+' done', flush=True)
        results[name] = {'gecerli': True, 'kural': rule, 'parametreler': parameters,
                         **ozetle(pd.concat(frames), tuple(args.seeds)), 'denetleyici_kaydi': audit}
        write(output/(name+'.json'), results[name])
    assessments = {}
    for candidate in candidates:
        name = candidate['name']
        vehicle = {base: evaluate_candidate(results[base], results[name], protocol['candidate_gates'],
                   baseline_seeds=args.seeds, candidate_seeds=args.seeds,
                   baseline_demand_hashes=demands[base], candidate_demand_hashes=demands[name])
                   for base in ('current', 'agent_recorded')}
        pedestrian = pedestrian_guard(results[name], results[candidate['rule']+'_60'])
        assessments[name] = {'accepted': all(v['accepted'] for v in vehicle.values()) and pedestrian['passed'],
                             'vehicle_gates': vehicle, 'pedestrian_guard': pedestrian}
    if hashes != input_hashes():
        raise RuntimeError('Inputs changed during evaluation; refusing final report')
    accepted = [name for name, value in assessments.items() if value['accepted']]
    summary_results = {name: {k:v for k,v in value.items() if k != 'denetleyici_kaydi'} for name,value in results.items()}
    payload = {'preregistration': registration, 'preregistration_sha256': sha256(output/'preregistration.json'),
               'input_hashes': hashes, 'demand_hashes': demands, 'results': summary_results, 'assessments': assessments,
               'accepted_candidates': accepted, 'active_policy_changed': False,
               'evidence_directory': output.relative_to(ROOT).as_posix(),
               'conclusion': 'All candidates failing any gate remain experimental. No policy is promoted automatically.'}
    write(output/'result.json', payload)
    print('REPORT '+str(output/'result.json'), flush=True)


if __name__ == '__main__':
    main()
