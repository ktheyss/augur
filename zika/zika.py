from __future__ import division, print_function
from collections import defaultdict
import sys
sys.path.append('')  # need to import from base
from base.io_util import make_dir, remove_dir, tree_to_json, write_json, myopen
from base.sequences import sequence_set, num_date
from base.tree import tree
from base.process import process
from base.frequencies import alignment_frequencies, tree_frequencies
from Bio import SeqIO
from Bio.SeqFeature import FeatureLocation
import numpy as np
from datetime import datetime

attribute_nesting = {'geographic location':['region', 'country', 'city'],}

if __name__=="__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Process virus sequences, build tree, and prepare of web visualization')
    parser.add_argument('-v', '--viruses_per_month', type = int, default = 100, help='number of viruses sampled per month')
    parser.add_argument('-r', '--raxml_time_limit', type = float, default = 1.0, help='number of hours raxml is run')
    parser.add_argument('--load', action='store_true', help = 'recover from file')
    params = parser.parse_args()

    lineage = 'zika'
    input_data_path = '../fauna/data/'+lineage
    store_data_path = 'store/'+lineage + '_'
    build_data_path = 'build/'+lineage + '_'

    zika = process(input_data_path = input_data_path,
                   store_data_path = store_data_path,
                   build_data_path = build_data_path,
                   reference='zika/metadata/zika_outgroup.gb',
                   proteins=['CA', 'PRO', 'MP', 'ENV', 'NS1', 'NS2A',
                             'NS2B', 'NS3', 'NS4A', 'NS4B', 'NS5'],
                   method='SLSQP')

    if params.load:
        zika.load()
    else:
        fasta_fields = {0:'strain', 2:'accession', 3:'date', 4:'region', 5:'country',
                        6:'division', 8:'db', 10:'authors', 11:'latitude', 12:'longitude'}
        zika.load_sequences(fields=fasta_fields)
        zika.seqs.filter(lambda s: s.attributes['date']>=datetime(2012,1,1).date() and
                                   s.attributes['date']< datetime(2017,1,1).date())
        zika.seqs.filter(lambda s: len(s.seq)>=2000)                                   
        dropped_strains = [
            "THA/PLCal_ZV/2013", "PLCal_ZV", # true strains, too basal for analysis
            "ZF36_36S", # possible contamination
            "Dominican_Republic/2016/PD2", "GD01", "GDZ16001" # true strains, but duplicates of other strains in dataset
        ]
        zika.seqs.filter(lambda s: s.id not in dropped_strains)
        zika.seqs.subsample(category = lambda x:(x.attributes['region'],
                                                 x.attributes['date'].year,
                                                 x.attributes['date'].month), threshold=1000)

        zika.align()
        zika.build_tree()

    zika.clock_filter(n_iqd=3, plot=True)
    zika.annotate_tree(Tc=0.005, timetree=True, reroot='best')
    zika.tree.geo_inference('region')
    zika.tree.geo_inference('country')
    zika.tree.geo_inference('division')
    zika.export(controls = attribute_nesting)
