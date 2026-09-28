import unittest
import pandas as pd
from engine import run, WorkflowError

class EngineTests(unittest.TestCase):
    def test_branch_join_and_aggregate(self):
        sources = {'orders': pd.DataFrame({'id':[1,2,3], 'amount':[10,20,30]}),
                   'people': pd.DataFrame({'id':[1,2,3], 'group':['A','A','B']})}
        nodes = [
            {'id':'o','op':'input','inputs':[],'config':{'source':'orders'}},
            {'id':'p','op':'input','inputs':[],'config':{'source':'people'}},
            {'id':'f','op':'filter','inputs':['o'],'config':{'column':'amount','operator':'>','value':'10'}},
            {'id':'j','op':'join','inputs':['f','p'],'config':{'left_key':'id','right_key':'id','how':'inner'}},
            {'id':'a','op':'aggregate','inputs':['j'],'config':{'group_by':['group'],'column':'amount','function':'sum'}}]
        result = run(nodes, sources)
        self.assertEqual(result['a'].set_index('group')['amount'].to_dict(), {'A':20,'B':30})
        self.assertEqual(len(sources['orders']), 3)

    def test_cycle_rejected(self):
        nodes = [{'id':'a','op':'sort','inputs':['b'],'config':{'columns':['x']}},
                 {'id':'b','op':'sort','inputs':['a'],'config':{'columns':['x']}}]
        with self.assertRaisesRegex(WorkflowError, 'Cycle detected'): run(nodes,{})

if __name__ == '__main__': unittest.main()
