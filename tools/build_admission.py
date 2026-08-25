from __future__ import annotations
import argparse, json

def evaluate(*, free_gb: float, threshold_gb: float, filesystem_writable: bool, reclaimable_safe_gb: float=0.0):
    admitted = filesystem_writable and free_gb >= threshold_gb
    blockers=[]
    if not filesystem_writable: blockers.append('filesystem_not_writable')
    if free_gb < threshold_gb: blockers.append('disk_admission_floor')
    return {
      'filesystem_writable': filesystem_writable,
      'free_gb': round(free_gb,2),
      'admission_threshold_gb': round(threshold_gb,2),
      'build_admitted': admitted,
      'blockers': blockers,
      'safe_reclaimable_gb': round(reclaimable_safe_gb,2),
      'free_after_safe_reclaim_gb': round(free_gb+reclaimable_safe_gb,2),
      'would_admit_after_safe_reclaim': filesystem_writable and free_gb+reclaimable_safe_gb >= threshold_gb,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--free-gb',type=float,required=True); p.add_argument('--threshold-gb',type=float,required=True)
    p.add_argument('--filesystem-writable',choices=['true','false'],required=True); p.add_argument('--safe-reclaimable-gb',type=float,default=0)
    a=p.parse_args(); print(json.dumps(evaluate(free_gb=a.free_gb,threshold_gb=a.threshold_gb,filesystem_writable=a.filesystem_writable=='true',reclaimable_safe_gb=a.safe_reclaimable_gb),sort_keys=True))
if __name__=='__main__': main()
