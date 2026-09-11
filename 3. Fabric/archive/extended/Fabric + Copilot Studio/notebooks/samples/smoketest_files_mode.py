"""Files-mode smoke test for the merged parser notebook.

Runs the entire parse + build chain in plain Python against the sample CSV at
Files/copilot_transcripts/conversationtranscripts.csv, asserts that all 7
output tables produce non-zero rows, and prints the row counts.

This is what CI runs to detect regressions in the parser without needing a
Fabric workspace or a Dataverse tenant.

Strategy: pull each code cell out of the notebook and exec() it in a single
namespace, with a minimal Spark/notebookutils shim that intercepts
.write.saveAsTable() calls and captures the dataframes for assertion.
"""
import json, sys, csv
from pathlib import Path

NB_PATH = Path(__file__).resolve().parent.parent / "Copilot_Agent_Transcript_Parser.ipynb"
SAMPLE  = Path(__file__).resolve().parent / "copilot_transcripts" / "conversationtranscripts.csv"

nb = json.loads(NB_PATH.read_text(encoding='utf-8'))

# Minimal shims so the notebook can exec without Spark/notebookutils.
import pandas as pd

class _Shim:
    """Mimic enough of pyspark.sql.SparkSession to keep the write loop happy."""
    def __init__(self):
        self.written = {}  # table_name -> pdf
        self.catalog = self
        self.read = _ReaderShim()
    def createDataFrame(self, pdf, schema=None):
        return _DataFrameShim(pdf, self)
    def tableExists(self, name):
        return False
    def sql(self, q):
        return None
    def table(self, name):
        raise NotImplementedError(f'spark.table({name!r}) not supported in smoke test')

class _ReaderShim:
    def __init__(self): self._opts = {}
    def option(self, k, v): return self
    def csv(self, path):
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        return _DataFrameShim(df, None)

class _DataFrameShim:
    def __init__(self, pdf, spark):
        self._pdf = pdf
        self._spark = spark
        self._mode = 'overwrite'
        self._opts = {}
    @property
    def columns(self): return list(self._pdf.columns)
    @property
    def write(self): return self
    def mode(self, m): self._mode = m; return self
    def option(self, k, v): self._opts[k] = v; return self
    def format(self, fmt): self._fmt = fmt; return self
    def saveAsTable(self, name):
        if self._spark is not None:
            self._spark.written[name] = self._pdf
    def alias(self, _): return self
    def toDF(self, *new_cols):
        if new_cols:
            self._pdf.columns = list(new_cols)
        return self
    def toPandas(self):
        return self._pdf

# Read the sample CSV here and stash it as `tx` so the parse cell can use it
sample_df = pd.read_csv(SAMPLE)
sample_df = sample_df.rename(columns={c: c.lower() for c in sample_df.columns})
print(f'Loaded sample: {len(sample_df)} transcripts, {len(sample_df.columns)} cols')

ns = {
    '__name__': '__main__',
    'spark': _Shim(),
    'pd': pd,
    'tx': sample_df,    # pre-loaded; cell 6 (ingest) sees SOURCE_MODE='files' and skips
}

# Drive: force files mode so cell 6 (ingest) does nothing â€” `tx` is already populated.
# Cell 7 (parse) checks `if SOURCE_MODE == 'files' or 'tx' not in dir() or tx is None` and reads
# TRANSCRIPTS_FILE in spark.read.csv mode â€” but we've pre-set `tx`, so it'll take the else branch.
# To keep things simple, we'll just exec cells 2 (CONFIG, with override), 7 onwards.

# First: exec CONFIG cell, then OVERRIDE SOURCE_MODE so it can't accidentally try Dataverse.
cells_by_index = nb['cells']
def get_code(i):
    assert cells_by_index[i]['cell_type'] == 'code', f'Cell {i} is not code'
    return ''.join(cells_by_index[i]['source'])

# Exec CONFIG (cell 2)
exec(get_code(2), ns)
ns['SOURCE_MODE'] = 'files'   # force smoke-test mode
ns['ABORT_ON_EMPTY'] = False  # we want the asserts to be in-Python, not raises
ns['OUTPUT_PREFIX'] = 'dbo'

# Skip Preflight (cell 4) â€” files mode skips it anyway, but it imports requests etc.
# We'll exec cell 6 (ingest) â€” it'll see SOURCE_MODE='files' and just print.
exec(get_code(6), ns)

# Cell 6 sets tx=None at the top of its body, then only re-assigns in dataverse/lakehouse
# modes â€” in files mode it just prints and leaves tx=None. Restore our pre-loaded sample.
ns['tx'] = sample_df

# tx still has our pre-loaded sample (cell 6 doesn't touch it in files mode).
# Exec cell 7 (parse) â€” it sees 'tx' in dir() AND SOURCE_MODE='files', so it ALSO tries
# to read from TRANSCRIPTS_FILE via spark.read. Patch that branch by ensuring tx is non-None.
# Actually re-reading cell 7: `if SOURCE_MODE == 'files' or 'tx' not in dir() or tx is None:`
# â†’ so files-mode reads from CSV via spark. Replace tx with our pre-loaded df by forcing
# SOURCE_MODE to anything else for the parse cell only.
parse_src = get_code(7)
# Patch out the spark.read fallback â€” our smoke test pre-loads `tx`.
parse_src = parse_src.replace(
    "if SOURCE_MODE == 'files' or 'tx' not in dir() or tx is None:",
    "if False:  # smoke test: tx is pre-loaded",
)
ns['SOURCE_MODE'] = 'files'
exec(parse_src, ns)

# Cells 9 (helpers), 11 (sessions), 13 (turns), 15 (5b), 17 (errors+subagents),
# 19 (agent_dim), 21 (agent_perf), 23 (5c enrichment) â€” exec in order.
for idx in (9, 11, 13, 15, 17, 19, 21, 23):
    src = get_code(idx)
    try:
        exec(src, ns)
    except Exception as e:
        print(f'\n*** Cell {idx} FAILED: {type(e).__name__}: {e}')
        import traceback; traceback.print_exc()
        sys.exit(1)

# Now manually run the write step (cell 25) but redirect to Pandas-only path
# (avoid the Spark + Delta dependencies). The shim captures saveAsTable calls.
write_src = get_code(25)
# Sub out pyspark imports + DeltaTable references so the cell doesn't fail on import.
write_src = write_src.replace(
    'from pyspark.sql.types import StructType, StructField, StringType',
    'StructType = lambda fields: None; StructField = lambda *a, **k: None; StringType = lambda: None'
)
# Skip merge code path entirely; we test only the default overwrite path.
ns['WRITE_MODE'] = 'overwrite'
try:
    exec(write_src, ns)
except Exception as e:
    print(f'\n*** Write cell FAILED: {type(e).__name__}: {e}')
    import traceback; traceback.print_exc()
    sys.exit(1)

# Now check what got "written"
written = ns['spark'].written
expected = ['dbo.agent_sessions', 'dbo.agent_turns', 'dbo.agent_errors',
            'dbo.agent_subagents', 'dbo.agent_catalogue', 'dbo.agent_performance',
            'dbo.agent_variables']

print('\n' + '=' * 60)
print('SMOKE TEST RESULT â€” row counts per table')
print('=' * 60)
ok = True
for tbl in expected:
    if tbl not in written:
        print(f'  âœ— {tbl:30}  MISSING')
        ok = False
        continue
    pdf = written[tbl]
    n = len(pdf)
    cols = len(pdf.columns)
    print(f'  {"âœ“" if n > 0 else "âœ—"} {tbl:30}  rows: {n:>6}   cols: {cols}')
    if n == 0:
        ok = False

# Show a sample of enrichment columns to confirm they populated
print('\nSpot-check enrichment populations:')
sessions = written.get('dbo.agent_sessions')
if sessions is not None:
    for col in ('is_authenticated', 'is_returning_user', 'session_outcome_explicit'):
        if col in sessions.columns:
            non_null = sessions[col].apply(lambda v: v not in (None, '', 'None')).sum()
            print(f'  agent_sessions.{col:35}  non-null: {non_null}/{len(sessions)}')

perf = written.get('dbo.agent_performance')
if perf is not None:
    for col in ('SessionOutcomeExplicit', 'TopicsStarted', 'LLMCallCount',
                'PluginCallCount', 'GenerativeResponseCount', 'MultiAgentSession',
                'ErrorCategory', 'TopicCompletionRate'):
        if col in perf.columns:
            non_null_or_nonzero = perf[col].apply(
                lambda v: v not in (None, '', 'None', '0', 0, 0.0, False, 'False')
            ).sum()
            print(f'  agent_performance.{col:35}  populated: {non_null_or_nonzero}/{len(perf)}')

variables = written.get('dbo.agent_variables')
if variables is not None and len(variables) > 0:
    print(f'\n  agent_variables (first 10 rows):')
    print(variables.head(10).to_string(index=False))

print('\n' + '=' * 60)
print(f'SMOKE TEST: {"PASSED âœ“" if ok else "FAILED âœ—"}')
print('=' * 60)
sys.exit(0 if ok else 1)

