import json
import pandas as pd
import streamlit as st
from engine import run, read_upload, WorkflowError, OPS

st.set_page_config(page_title='FlowForge', page_icon='🔀', layout='wide')
st.title('FlowForge')
st.caption('Build and run repeatable data preparation workflows')

if 'nodes' not in st.session_state: st.session_state.nodes = []
if 'sources' not in st.session_state: st.session_state.sources = {}

with st.sidebar:
    st.header('Data sources')
    uploads = st.file_uploader('Upload CSV, Excel, or Parquet', type=['csv', 'xlsx', 'parquet'], accept_multiple_files=True)
    for file in uploads or []:
        if file.name not in st.session_state.sources:
            try: st.session_state.sources[file.name] = read_upload(file.name, file.getvalue())
            except Exception as exc: st.error(f'{file.name}: {exc}')
    st.write('Loaded:', ', '.join(st.session_state.sources) or 'none')
    st.header('Workflow')
    imported = st.file_uploader('Import workflow JSON', type=['json'], key='workflow')
    if imported and st.button('Load workflow'):
        try:
            payload = json.load(imported)
            if not isinstance(payload, list) or any(not isinstance(n, dict) or not {'id','op','inputs','config'} <= n.keys() for n in payload):
                raise ValueError('Expected a list of nodes with id, op, inputs, and config')
            st.session_state.nodes = payload
            st.rerun()
        except (ValueError, json.JSONDecodeError) as exc: st.error(str(exc))
    st.download_button('Save workflow JSON', json.dumps(st.session_state.nodes, indent=2), 'workflow.json', 'application/json')

nodes = st.session_state.nodes
ids = [n['id'] for n in nodes]
with st.expander('Add a step', expanded=True):
    with st.form('add_step'):
        node_id = st.text_input('Step ID', placeholder='e.g. filter_orders')
        op = st.selectbox('Operation', sorted(OPS))
        inputs = st.multiselect('Input steps (choose two for join or union)', ids)
        source = st.selectbox('Source file for input step', list(st.session_state.sources) or [''], disabled=op != 'input')
        config_text = st.text_area('Configuration JSON', value='{}', help='See the examples and operation reference in README.md')
        added = st.form_submit_button('Add step')
    if added:
        try:
            config = json.loads(config_text)
            if not isinstance(config, dict): raise ValueError('Configuration must be an object')
            if op == 'input': config['source'] = source
            if not node_id or node_id in ids: raise ValueError('Enter a unique step ID')
            required = 0 if op == 'input' else 2 if op in ('join', 'union') else 1
            if len(inputs) != required: raise ValueError(f'{op} requires {required} input(s)')
            nodes.append({'id': node_id, 'op': op, 'inputs': inputs, 'config': config})
            st.rerun()
        except ValueError as exc: st.error(str(exc))

st.subheader('Steps')
if not nodes: st.info('Upload a file, then add an input step to begin.')
for n in nodes:
    with st.expander(f"{n['id']} · {n['op']}  ← {', '.join(n['inputs']) or 'source'}"):
        edited = st.text_area('Configuration JSON', json.dumps(n['config'], indent=2), key=f"edit_{n['id']}")
        a, b = st.columns(2)
        if a.button('Apply configuration', key=f"apply_{n['id']}"):
            try:
                obj = json.loads(edited)
                if not isinstance(obj, dict): raise ValueError('Expected JSON object')
                n['config'] = obj
                st.rerun()
            except ValueError as exc: st.error(str(exc))
        if b.button('Delete step', key=f"delete_{n['id']}"):
            if any(n['id'] in other['inputs'] for other in nodes): st.error('Delete dependent steps first.')
            else:
                nodes.remove(n)
                st.rerun()

if st.button('Run workflow', type='primary', disabled=not nodes):
    try: st.session_state.outputs = run(nodes, st.session_state.sources)
    except WorkflowError as exc:
        st.session_state.pop('outputs', None)
        st.error(str(exc))
if 'outputs' in st.session_state:
    outputs = st.session_state.outputs
    selected = st.selectbox('Inspect output', list(outputs))
    frame = outputs[selected]
    st.metric('Rows', len(frame))
    st.metric('Columns', len(frame.columns))
    st.dataframe(frame.head(1000), use_container_width=True)
    st.download_button('Export selected output as CSV', frame.to_csv(index=False).encode(), f'{selected}.csv', 'text/csv')
