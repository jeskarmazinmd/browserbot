# Independent main-strategy paper output switches

The LIVE runner calculates source signals even when their own paper output is
switched off. Descendant modules can therefore remain enabled when a source
module's paper output is disabled. This retains each descendant's existing
entry rule: C1 still requires the B-shaped flash setup, for example.

The September 23 review pauses 74 BA paper outputs in the source-controlled
`PAUSED_BIDASK_PAPER_IDS` set in `strategies/output_switches.py`. This pause
also removes their BA-suffixed names from active performance snapshots. A
volume switch cannot override a source-controlled pause; remove an ID from
that set and redeploy to resume it. The live NH015 broker path is separate.

Place a JSON object at `/data/strategy_output_switches.json` on the Fly volume:

```json
{"B": false, "C1": true}
```

Keys are exact, uppercase strategy IDs. `false` suppresses a module's new
independent BA entries and removes it from the active all-engine snapshot on
the next report refresh. An absent key or `true` enables its output. The runner
reads the file as signals arrive, so a change does not require a deploy.
Existing open positions continue to receive exit updates; historical ledgers
are not deleted. Write changes atomically (write a temporary file then rename)
so the runner never reads a partially written control file.

The switches cover main-runner flash, minute, and derived strategy paper
outputs. Native research workers, factory-generated outputs, replay, and
broker execution have their own controls. This change does not make derived
signal definitions independent of their source market setup; it makes their
paper output independent of the source module's output switch.
