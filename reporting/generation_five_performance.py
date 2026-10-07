"""G5 actual fills; fresh executable marks; no hindsight resizing or carry claims."""
import json
from executable_paper_engine import executable_mark
from generation_five_paper_tracker import FILE_STEM, IDS
from strategies import generation_five as g5
from paper_outcome_tracker import NY,_utc
from reporting.generation_one_performance import calculate_generation_one

def calculate_generation_five(root,day,cutoff,marks,quote_for):
    def fresh_quote(symbol,context):
        quote=quote_for(symbol,context)
        mark=executable_mark(quote,action='SELL',now=cutoff,max_quote_age_ms=5000)
        return quote if mark['state']=='EXECUTABLE' and mark['quote_age_ms']>=0 else {}
    modules,diagnostics=calculate_generation_one(root,day,cutoff,marks,fresh_quote,
        file_stem=FILE_STEM,ids=IDS,flash_catalog=g5,
        minute_catalog=g5.MINUTE_CATALOG,engine_name='generation_five_bidask_independent')
    # An overnight carry needs prior-close executable mark provenance to quote a
    # daily marked return. Do not silently drop that position or invent a mark.
    carry=set();entries={};path=root/(FILE_STEM+'_outcomes.jsonl')
    if path.exists():
        with path.open() as handle:
            for line in handle:
                try:
                    r=json.loads(line);sid=r['strategy_id'];setup=r['setup_id'];event=r['event_type']
                    when=_utc(r.get('exit_timestamp') or r.get('entry_timestamp') or r['recorded_at'])
                except (ValueError,KeyError,TypeError):continue
                if sid not in IDS or when>cutoff:continue
                if event=='PAPER_ENTRY':entries[setup]=r
                elif event in {'PAPER_PARTIAL_EXIT','PAPER_EXIT'} and setup in entries:
                    entered=_utc(entries[setup]['entry_timestamp']).astimezone(NY).date().isoformat()
                    exited=when.astimezone(NY).date().isoformat()
                    if entered<day and exited==day:carry.add(sid)
                    if event=='PAPER_EXIT':entries.pop(setup)
        for r in entries.values():
            if _utc(r['entry_timestamp']).astimezone(NY).date().isoformat()<day:carry.add(r['strategy_id'])
    for sid in carry:modules.pop(sid+'BA',None)
    diagnostics['overnight_carry_unverified_modules']=len(carry)
    for row in modules.values():row['accounting']='actual quantities; daily equal-start $5k; no strategy aggregation'
    return modules,diagnostics
