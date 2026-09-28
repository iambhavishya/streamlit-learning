"""Small, deterministic tabular workflow engine."""
from __future__ import annotations
import io
import re
from dataclasses import dataclass
import pandas as pd

OPS = {'input', 'select', 'filter', 'formula', 'sort', 'sample', 'aggregate', 'join', 'union', 'deduplicate', 'rename'}

@dataclass
class WorkflowError(Exception):
    node: str
    message: str
    def __str__(self):
        return f'{self.node}: {self.message}'

def _columns(frame, names, node):
    missing = set(names) - set(frame.columns)
    if missing:
        raise WorkflowError(node, f'Missing columns: {", ".join(sorted(missing))}')

def run(nodes: list[dict], sources: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Execute a directed acyclic graph in dependency order, returning each node output."""
    by_id = {n['id']: n for n in nodes}
    if len(by_id) != len(nodes):
        raise WorkflowError('workflow', 'Node IDs must be unique')
    if any(n.get('op') not in OPS for n in nodes):
        raise WorkflowError('workflow', 'Unknown operation')
    outputs: dict[str, pd.DataFrame] = {}
    visiting: set[str] = set()
    def evaluate(node_id: str) -> pd.DataFrame:
        if node_id in outputs:
            return outputs[node_id]
        if node_id in visiting:
            raise WorkflowError(node_id, 'Cycle detected')
        if node_id not in by_id:
            raise WorkflowError(node_id, 'Referenced node does not exist')
        visiting.add(node_id)
        node = by_id[node_id]
        op = node['op']
        args = node.get('config', {})
        parents = node.get('inputs', [])
        expected = 0 if op == 'input' else 2 if op in ('join', 'union') else 1
        if len(parents) != expected:
            raise WorkflowError(node_id, f'{op} requires {expected} input(s)')
        frames = [evaluate(parent) for parent in parents]
        try:
            if op == 'input':
                key = args['source']
                if key not in sources:
                    raise WorkflowError(node_id, f'Source {key!r} is not loaded')
                result = sources[key].copy()
            elif op == 'select':
                cols = args['columns']
                _columns(frames[0], cols, node_id)
                result = frames[0][cols].copy()
            elif op == 'filter':
                col, comparator, value = args['column'], args['operator'], args['value']
                _columns(frames[0], [col], node_id)
                series = frames[0][col]
                if comparator in ('contains', 'not contains'):
                    mask = series.astype(str).str.contains(str(value), case=False, regex=False, na=False)
                    if comparator == 'not contains': mask = ~mask
                elif comparator in ('is null', 'is not null'):
                    mask = series.isna() if comparator == 'is null' else series.notna()
                else:
                    if pd.api.types.is_numeric_dtype(series): value = pd.to_numeric(value)
                    elif pd.api.types.is_datetime64_any_dtype(series): value = pd.to_datetime(value)
                    mask = {'==': lambda: series == value, '!=': lambda: series != value,
                            '>': lambda: series > value, '>=': lambda: series >= value,
                            '<': lambda: series < value, '<=': lambda: series <= value}[comparator]()
                result = frames[0].loc[mask.fillna(False)].copy()
            elif op == 'formula':
                # Explicit supported expressions, avoiding arbitrary Python evaluation.
                col, action, target = args['column'], args['action'], args['target']
                _columns(frames[0], [col], node_id)
                result = frames[0].copy()
                s = result[col]
                if action == 'uppercase': result[target] = s.astype('string').str.upper()
                elif action == 'lowercase': result[target] = s.astype('string').str.lower()
                elif action == 'trim': result[target] = s.astype('string').str.strip()
                elif action == 'length': result[target] = s.astype('string').str.len()
                elif action == 'to number': result[target] = pd.to_numeric(s, errors='coerce')
                elif action == 'fill null': result[target] = s.fillna(args.get('value', ''))
                elif action == 'multiply': result[target] = pd.to_numeric(s, errors='coerce') * float(args['value'])
                elif action == 'add': result[target] = pd.to_numeric(s, errors='coerce') + float(args['value'])
                else: raise WorkflowError(node_id, f'Unknown formula action {action}')
            elif op == 'sort':
                cols = args['columns']; _columns(frames[0], cols, node_id)
                result = frames[0].sort_values(cols, ascending=args.get('ascending', True)).reset_index(drop=True)
            elif op == 'sample': result = frames[0].head(int(args['rows'])).copy()
            elif op == 'deduplicate':
                cols = args['columns']; _columns(frames[0], cols, node_id)
                result = frames[0].drop_duplicates(subset=cols).reset_index(drop=True)
            elif op == 'rename': result = frames[0].rename(columns=args['mapping']).copy()
            elif op == 'aggregate':
                groups, column, func = args['group_by'], args['column'], args['function']
                _columns(frames[0], groups + [column], node_id)
                if groups:
                    result = frames[0].groupby(groups, dropna=False)[column].agg(func).reset_index()
                else:
                    result = pd.DataFrame({f'{column}_{func}': [frames[0][column].agg(func)]})
            elif op == 'join':
                left, right = args['left_key'], args['right_key']
                _columns(frames[0], [left], node_id); _columns(frames[1], [right], node_id)
                result = frames[0].merge(frames[1], left_on=left, right_on=right,
                                         how=args.get('how', 'inner'), suffixes=('_left', '_right'))
            elif op == 'union': result = pd.concat(frames, ignore_index=True, sort=False)
        except WorkflowError:
            raise
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise WorkflowError(node_id, str(exc)) from exc
        finally:
            visiting.remove(node_id)
        outputs[node_id] = result
        return result
    for node in nodes: evaluate(node['id'])
    return outputs

def read_upload(name: str, data: bytes) -> pd.DataFrame:
    if name.lower().endswith('.csv'): return pd.read_csv(io.BytesIO(data))
    if name.lower().endswith('.xlsx'): return pd.read_excel(io.BytesIO(data))
    if name.lower().endswith('.parquet'): return pd.read_parquet(io.BytesIO(data))
    raise ValueError('Upload CSV, XLSX, or Parquet files')
