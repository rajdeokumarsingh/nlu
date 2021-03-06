#coding=UTF-8
'''
Creates AMR fragments for named entities.

@author: Nathan Schneider (nschneid)
@since: 2012-07-30
'''
from __future__ import print_function
import os, sys, re, codecs, fileinput, json

import pipeline
from pipeline import new_concept_from_token, choose_head, new_concept, new_amr_from_old, parent_edges

'''
Example input, from wsj_0002.0:

"bbn_ne": { [
      0, 
      1, 
      "Rudolph Agnew", 
      "PERSON", 
      "", 
      "chairman", 
      false
    ], ...,

    [
      10, 
      13, 
      "Consolidated Gold Fields PLC", 
      "ORGANIZATION", 
      "CORPORATION", 
      "", 
      false
    ], ...}
'''





def main(sentenceId, jsonFile, tokens, ww, wTags, depParse, inAMR, alignment, completed):
    amr = inAMR
    triples = set() # to add to the AMR
    
    entities = pipeline.loadBBN(jsonFile)
    for i,j,name,coarse,fine,raw in entities:
        
        if raw.startswith('<TIMEX'): continue  # use the timex module (sutime output) instead
        
        h = choose_head(range(i,j+1), depParse, 
                        fallback=lambda frontier: max(frontier) if len(frontier)==2 and ww[min(frontier)]=='than' else False)
                        # ^ dirty hack: in 'more than 3 times' (wsj_0003.12), [more than 3] is a value expression 
                        # but 'than' and '3' both attach to 'times' in the dependency parse.
        #print((i,j),name,h,depParse[h+1]['dep'], file=sys.stderr)
        
        x = alignment[:h] # index of variable associated with i's head, if any
        
        if raw.startswith('<NUMEX'):
            if coarse in ['MONEY','CARDINAL','PERCENT']:
                # get normalized value from Stanford tools
                v = wTags[h]["NormalizedNamedEntityTag"]
                
                wrapper = None
                if v[0] in '<>~':
                    if len(v)==1:
                        print('Warning: Unexpected NormalizedNamedEntityTag:',v,'for',raw, file=sys.stderr)
                    else:
                        if v[1]=='=':
                            reln = v[:2]
                            v = v[2:]
                        else:
                            reln = v[0]
                            v = v[1:]
                        concept = {'<': 'less-than', '>': 'more-than', '<=': 'no-more-than', '>=': 'at-least', '~': 'about'}[reln]
                        wrapper = new_concept_from_token(amr, alignment, h, depParse, wTags, concept=concept)
                    
                if coarse=='MONEY':
                    m = re.match(r'^([\$¥£])(\d+\.\d+(E-?\d+)?)$', v)
                    if not m:
                        assert False,v
                    u = m.group(1)
                    v = m.group(2)
                elif coarse=='PERCENT':
                    m = re.match(r'^%(\d+\.\d+(E-?\d+)?)$', v)
                    if not m:
                        assert False,v
                    v = m.group(1)
                
                try:
                    v = float(v)
                    if str(v).endswith('.0'):
                        v = int(v)
                except ValueError:
                    pass
                
                if (wrapper is None or coarse=='MONEY') and not (x or x==0): # need a new variable
                    kind = {'MONEY': 'monetary-quantity', 'PERCENT': 'percentage-entity'}.get(coarse, coarse.upper())
                    if wrapper is None: # if there is a wrapper concept (e.g. 'more-than'), it is aligned, so don't provide an alignment for x
                        x = new_concept_from_token(amr, alignment, h, depParse, wTags, concept=kind)
                    else:
                        x = new_concept(kind, amr)
                
                if (x or x==0):
                    triples.add((str(x), 'value' if coarse=='PERCENT' else 'quant', v))
                    if wrapper is not None:
                        triples.add((str(wrapper), 'op1', str(x)))
                elif wrapper is not None:
                        triples.add((str(wrapper), 'op1', v))   # e.g. more-than :op1 41
                
                
                if coarse=='MONEY':
                    y = new_concept({'$': 'dollar', '¥': 'yen', '£': 'pound'}[u.encode('utf-8')], amr)
                    triples.add((str(x), 'unit', str(y)))
            elif coarse=='ORDINAL':
                pass    # skip--no special treatment in AMR guidelines, though the normalized value could be used
            else:
                assert False,(i,j,raw)
        elif coarse.endswith('_DESC'):
            # make the phrase head word the AMR head concept
            # (could be a multiword term, like Trade Representative)
            if not (x or x==0): # need a new variable
                x = new_concept_from_token(amr, alignment, h, depParse, wTags)
                triples.add((str(x), '-DUMMY', '')) # ensure the concept participates in some triple so it is printed
        else:
            if coarse.lower()=='person' and i>0 and ww[i-1] and ww[i-1].lower() in ['mr','mr.','mister','master','sir','mrs','mrs.','miss']:
                # Extend the NE to include formal titles that do not get concepts
                name = ww[i-1]+' '+name
                i -= 1

            if not (x or x==0): # need a new variable
                ne_class = fine.lower().replace('other','') or coarse.lower()
                concept, amr_name = amrify(ne_class, name)
                x = new_concept_from_token(amr, alignment, h, depParse, wTags, 
                                concept=pipeline.token2concept(concept)+'-FALLBACK')
                # -FALLBACK indicates extra information not in the sentence (NE class)
                n = new_concept('name', amr)
                triples.add((str(x), 'name', str(n)))
                for iw,w in enumerate(amr_name.split()):
                    triples.add((str(n), 'op'+str(iw+1), '"'+w+'"'))
                    
        
        for k in range(i,j+1):
            assert not completed[0][k]
            completed[0][k] = True
            #print('completed token',k)
            if k!=h:
                for link in parent_edges(depParse[k]):
                    completed[1][link] = True  # we don't need to attach non-head parts of names anywhere else
    
    amr = new_amr_from_old(amr, new_triples=list(triples))

    return depParse, amr, alignment, completed

# TODO: incorporate Mr., Mrs., etc. in the name
# TODO: Dr. -> doctor

# TODO: find a real list of nationalities -> country names
NATIONALITIES = {'Chinese': 'China', 'Balinese': 'Bali', 'French': 'France', 'Dutch': 'Netherlands', 
                 'Irish': 'Ireland', 'Scottish': 'Scotland', 'Welsh': 'Wales', 'English': 'England', 'British': 'Britain', 
                 'Finnish': 'Finland', 'Swedish': 'Sweden', 'Spanish': 'Spain',
                 'Somali': 'Somalia', 'Hawaiian': 'Hawaii', 'Brazilian': 'Brazil', 
                 'Kentuckian': 'Kentucky', 'Italian': 'Italy', 'German': 'Germany', 'Norwegian': 'Norway', 
                 'Belgian': 'Belgium', 'Washingtonian': 'Washington', 'Canadian': 'Canada'}
def amrify(ne_class, name):
    concept = ne_class
    if ne_class=='corporation':
        concept = 'company'
    elif ne_class=='nationality':
        concept = 'country'
        if name in NATIONALITIES:
            name = NATIONALITIES[name]
        else:
            name = re.sub(r'i$', '', name)  # Iraqi -> Iraq
            name = re.sub(r'ian$', 'ia', name)   # Russian -> Russia, Australian -> Australia, Indian -> India
            name = re.sub(r'([aeiouy])an$', r'\1', name) # Tennesseean -> Tennessee, New Jerseyan -> New Jersey
            name = re.sub(r'an$', 'a', name)    # Moldovan -> Moldova, Sri Lankan -> Sri Lanka, Rwandan -> Rwanda, American -> America
            name = re.sub(r'ese$', '', name)    # Japanese -> Japan
        
    return concept, name
    
