#!/usr/bin/env python2.7
'''
Driver and utilities for English-to-AMR pipeline.
'''
from __future__ import print_function
import os, sys, re, codecs, fileinput, json

from dev.amr.amr import Amr
from alignment import Alignment

def main(sentenceId):
    # load dependency parse from sentence file
    ww, wTags, depParse = loadDepParse(sentenceId)
    del ww
    del wTags
    # TODO: ww and wTags are bad right now, because they don't account for empty element tokens
    # use depParse instead.
    
    # pipeline steps
    import nes, vprop, adjsAndAdverbs

    # initialize input to first pipeline step
    token_accounted_for = [False]*len(depParse)
    '''Has the token been accounted for yet in the semantics?'''
    
    edge_accounted_for = {(dep['gov_idx'],m): False for m in range(len(depParse)) if depParse[m] for dep in depParse[m]}
    '''Has the dependency edge been accounted for yet in the semantics?'''
    
    completed = token_accounted_for, edge_accounted_for
    
    amr = Amr()
    alignments = Alignment()

    # serially execute pipeline steps
    for m in [nes, vprop, adjsAndAdverbs]:
        depParse, amr, alignments, completed = m.main(sentenceId, depParse, amr, alignments, completed)
        #print(' '.join(ww))
        print(repr(amr), file=sys.stderr)
        print('Completed:',[depParse[i][0]['dep'] for i,v in enumerate(completed[0]) if v and depParse[i]], file=sys.stderr)
        print(alignments, [deps[0]['dep'] for deps in depParse if deps and not completed[0][deps[0]['dep_idx']]], file=sys.stderr)
        print(amr, file=sys.stderr)

    # TODO: output

def token2concept(t):
    return re.sub(r'[^A-Za-z0-9-]', '', t).lower() or '??'


def loadBBN(sentenceId):
    jsonFile = 'examples/'+sentenceId+'.json'
    with codecs.open(jsonFile, 'r', 'utf-8') as jsonF:
        return json.load(jsonF)['bbn_ne']

def loadVProp(sentenceId):
    jsonFile = 'examples/'+sentenceId+'.json'
    with codecs.open(jsonFile, 'r', 'utf-8') as jsonF:
        return json.load(jsonF)['prop']

def loadDepParse(sentenceId):
    jsonFile = 'examples/'+sentenceId+'.json'
    with codecs.open(jsonFile, 'r', 'utf-8') as jsonF:
        sentJ = json.load(jsonF)
        deps_concise = sentJ['stanford_dep']
        deps = []
        for entry in deps_concise:
            while len(deps)<entry['dep_idx']:
                deps.append(None)   # dependency root, puncutation, or function word incorporated into a dependecy relation
            if entry['dep_idx']==len(deps):
                deps.append([])
            if entry['gov_idx']==-1:    # root
                entry['gov_idx'] = None
            deps[-1].append(entry)  # can be multiple entries for a token, because tokens can have multiple heads
        ww, wTags, = zip(*sentJ['words'])
        return ww, wTags, deps

def parents(depParseEntry):
    return [dep['dep_idx'] for dep in depParseEntry] if depParseEntry else []

def parent_edges(depParseEntry):
    return [(dep['gov_idx'],dep['dep_idx']) for dep in depParseEntry] if depParseEntry else []

def choose_head(tokenIndices, depParse):
    # restricted version of least common subsumer:
    # assume that for every word in the NE, 
    # all words on the ancestor path up to the NE's head 
    # are also in the NE
    frontier = set(tokenIndices)    # should end up with just 1 (the head)
    for itm in set(frontier):
        if not depParse[itm] or all((depitm['gov_idx'] in tokenIndices) for depitm in depParse[itm]):
            frontier.remove(itm)
    assert len(frontier)==1,(tokenIndices,frontier)
    return next(iter(frontier))
    

def new_concept(concept, amr, alignment=None, alignedToken=None):
    # new variable
    x = len(amr.node_to_concepts)
    
    amr.node_to_concepts[str(x)] = concept
    
    if alignedToken is not None:
        alignment.link(x, alignedToken)
    
    return x    # variable, as an integer


if __name__=='__main__':
    sentId = sys.argv[1]
    main(sentId)