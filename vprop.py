'''
Creates AMR fragments for verb propositions (PropBank-style semantic role structures).

@author: Nathan Schneider (nschneid)
@since: 2012-07-31
'''
from __future__ import print_function
import os, sys, re, codecs, fileinput, json

import pipeline, config, timex
from pipeline import Atom, choose_head, new_concept_from_token, new_amr_from_old

'''
Example input, from wsj_0002.0:

"prop": [
    {
      "inflection": "-----", 
      "basepos": "v", 
      "baseform": "name", 
      "args": [
        [
          "rel", 
          "16:0", 
          16, 
          16, 
          "named"
        ], 
        [
          "ARG1", 
          "17:0", 
          0, 
          14, 
          "Rudolph Agnew , 55 years old and former chairman of Consolidated Gold Fields PLC ,"
        ], 
        [
          "ARG2", 
          "18:2", 
          18, 
          26, 
          "*PRO*-2 a nonexecutive director of this British industrial conglomerate"
        ], 
        [
          "LINK-PCR", 
          "17:0*17:0", 
          null, 
          null, 
          ""
        ]
      ], 
      "roleset": "name.01"
    }
'''





def main(sentenceId, jsonFile, tokens, ww, wTags, depParse, inAMR, alignment, completed):
    amr = inAMR
    triples = set() # to add to the AMR
    
    props = pipeline.loadVProp(jsonFile)
    
    # add all predicates first, so the roleset properly goes into the AMR
    for prop in props:
        baseform, roleset = prop["baseform"], prop["frame"]
        
        preds = {tuple(arg[:5]) for arg in prop["args"] if arg[0]=='rel'}
        assert len(preds)==1
        pred = next(iter(preds))
        assert pred[2]==pred[3] # multiword predicates?
        ph = pred[2]    # predicate head
        if ph is None: continue  # TODO: improve coverage of complex spans
        
        px = alignment[:ph]
        if not (px or px==0):
            px = new_concept_from_token(amr, alignment, ph, depParse, wTags, concept=pipeline.token2concept(roleset.replace('.','-')))
            if len(prop["args"])==1 or prop["args"][1][0].startswith('LINK'):
                triples.add((str(px), '-DUMMY', ''))
        completed[0][ph] = True
        
    # now handle arguments
    for prop in props:
        baseform, roleset = prop["baseform"], prop["frame"]
        
        pred = [arg for arg in prop["args"] if arg[0]=='rel'][0]
        ph = pred[2]    # predicate head
        if ph is None: continue # TODO: improve coverage of complex spans
        px = alignment[:ph]
        
        for rel,treenode,i,j,yieldS,_ in prop["args"]:
            if i is None or j is None: continue # TODO: special PropBank cases that need further work
            if rel in ['rel', 'LINK-PCR', 'LINK-SLC']: continue
            assert rel[:3]=='ARG'
            if i==j:
                #assert depParse[i], (tokens[i],rel,treenode,yieldS)
                if depParse[i] is None: continue    # TODO: is this appropriate? e.g. in wsj_0003.0
            #print(roleset,rel,i,j,yieldS)
            h = choose_head(range(i,j+1), depParse)
            if h is None: continue  # TODO: temporary?
            x = alignment[:h] # index of variable associated with i's head, if any
            
            # handle general proposition arguments
            if str(alignment[:h]) in amr.node_to_concepts:
                rel, amr.node_to_concepts[str(alignment[:h])] = common_arg(rel, amr.get_concept(str(alignment[:h])))
            else:
                drels = [dep["rel"] for dep in depParse[h]]
                rel = common_arg(rel, drels=drels)
            
            # verb-specific argument types
            if rel=='ARGM-MOD':
                if yieldS=='will':
                    pass    # skip this auxiliary
                else:
                    continue # handle modal in a later module
            elif isinstance(rel,tuple):
                rel, val = rel
                assert isinstance(val,Atom)
                triples.add((str(px), rel, val))
            else:
                if not (x or x==0): # need a new variable
                    x = new_concept_from_token(amr, alignment, h, depParse, wTags)
                triples.add((str(px), rel, str(x)))
            
            completed[0][h] = True

            # if SRL argument link corresponds to a dependency edge, mark that edge as complete
            if (ph,h) in completed[1]:
                completed[1][(ph,h)] = True
                #print('completed ',(ph,h))
            if (h,ph) in completed[1]:  # also for reverse direction
                completed[1][(h,ph)] = True
                #print('completed ',(ph,h))
    
    #print(triples)
    amr = new_amr_from_old(amr, new_triples=list(triples))

    return depParse, amr, alignment, completed

def common_arg(rel, concept=None, drels=None):
    '''
    Kind of argument that may occur in a noun or verb proposition. 
    Exceptions include ARGM-MOD (modal), which is verb-specific.
    '''
    if True:
            newrel = rel.replace('-REF','')
            newconcept = concept
            if rel=='ARGM-TMP':
                if concept is not None and any(ttyp in concept.split('-') for ttyp in timex.Timex3Entity.valid_types):
                    if 'DURATION' in concept.split('-'):
                        newrel = 'duration'
                        newconcept = concept.replace('-DURATION','')
                    else:
                        newrel = 'time'
                        newconcept = concept.replace('-DATE_RELATIVE','').replace('-DATE','').replace('-SET','')
                else:   # no TIMEX information
                    if concept is not None:
                        if config.verbose or config.warn: print('Warning: ARGM-TMP not a known time expression',(concept,drels), file=sys.stderr)
                    # fallback: see if it looks syntactically like a temporal modifier
                    if drels:
                        if 'tmod' in drels:
                            newrel = 'time'
                        elif 'amod' in drels:
                            newrel = 'mod' # e.g. 'former' -- temporal but not itself a time
            elif rel=='ARGM-NEG':
                newrel = 'polarity'
                newconcept = Atom('-')
            elif rel[:5]=='ARGM-':
                newrel = {'CAU': 'cause',
                          'COM': 'accompanier',  # is this right? ARGM-COM is used for two people performing an action together
                          'DIR': 'direction',
                          'EXT': 'degree',  # extent
                          'GOL': 'beneficiary',  # could also be :destination
                          'LOC': 'location',  # possibly also :source. look at preposition?
                          'MNR': 'manner',
                          'PRP': 'purpose',
                          'PNC': 'purpose',  # purpose not cause
                          }.get(rel[5:], 'mod')  
                # will default to :mod for: ADV, ADJ, DIS(course), DSP (direct speech), PRD (secondary predication), REC (reciprocal), LVB (light verb of nominal proposition)

    return (newrel, newconcept) if newconcept is not None else newrel
