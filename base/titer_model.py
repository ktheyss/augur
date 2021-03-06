from __future__ import division, print_function
import numpy as np
import time
from collections import defaultdict
from base.io_util import myopen
from itertools import izip
import pandas as pd

TITER_ROUND=4

class titers(object):
    '''
    this class decorates as phylogenetic tree with titer measurements and infers
    different models that describe titer differences in a parsimonious way.
    Two additive models are currently implemented, the tree and the subsitution
    model. The tree model describes titer drops as a sum of terms associated with
    branches in the tree, while the substitution model attributes titer drops to amino
    acid mutations. More details on the methods can be found in
    Neher et al, PNAS, 2016
    '''

    def __init__(self, tree, titer_fname = 'data/HI_titers.txt', serum_Kc=0, **kwargs):
        self.kwargs = kwargs
        # set self.tree and dress tree with a number of extra attributes
        self.prepare_tree(tree)

        # read the titers and assign to self.titers, in addition
        # self.strains and self.sources are assigned
        self.read_titers(titer_fname)
        self.normalize_titers()
        self.serum_Kc=serum_Kc


    def prepare_tree(self, tree):
        self.tree = tree # not copied, just linked
        # produce dictionaries that map node names to nodes regardless of capitalization
        self.node_lookup = {n.name:n for n in tree.get_terminals()}
        self.node_lookup.update({n.name.upper():n for n in tree.get_terminals()})
        self.node_lookup.update({n.name.lower():n for n in tree.get_terminals()})

        # have each node link to its parent. this will be needed for walking up and down the tree
        self.tree.root.up=None
        for node in self.tree.get_nonterminals():
            for c in node.clades:
                c.up = node


    def read_titers(self, fname):
        self.titer_fname = fname
        if "excluded_tables" in self.kwargs:
            self.excluded_tables = self.kwargs["excluded_tables"]
        else:
            self.excluded_tables = []

        strains = set()
        measurements = defaultdict(list)
        sources = set()
        with myopen(fname, 'r') as infile:
            for line in infile:
                entries = line.strip().split()
                test, ref_virus, serum, src_id, val = (entries[0], entries[1],entries[2],
                                                        entries[3], float(entries[4]))
                ref = (ref_virus, serum)
                if src_id not in self.excluded_tables:
                    try:
                        measurements[(test, (ref_virus, serum))].append(val)
                        strains.update([test, ref_virus])
                        sources.add(src_id)
                    except:
                        print(line.strip())
        self.titers = measurements
        self.strains = list(strains)
        self.sources = list(sources)
        print("Read titers from",self.titer_fname, 'found:')
        print(' ---', len(self.strains), "strains")
        print(' ---', len(self.sources), "data sources")
        print(' ---', sum([len(x) for x in measurements.values()]), " total measurements")


    def normalize(self, ref, val):
        consensus_func = np.mean
        return consensus_func(np.log2(self.autologous_titers[ref]['val'])) \
                - consensus_func(np.log2(val))

    def determine_autologous_titers(self):
        autologous = defaultdict(list)
        all_titers_per_serum = defaultdict(list)
        for (test, ref), val in self.titers.iteritems():
            if ref[0].upper() in self.node_lookup:
                all_titers_per_serum[ref].append(val)
                if ref[0]==test:
                    autologous[ref].append(val)

        self.autologous_titers = {}
        for serum in all_titers_per_serum:
            if serum in autologous:
                self.autologous_titers[serum] = {'val':autologous[serum], 'autologous':True}
                print("autologous titer found for",serum)
            else:
                if len(all_titers_per_serum[serum])>10:
                    self.autologous_titers[serum] = {'val':np.max(all_titers_per_serum[serum]),
                                                     'autologous':False}
                    print(serum,": using max titer instead of autologous,",
                          np.max(all_titers_per_serum[serum]))
                else:
                    print("discarding",serum,"since there are only ",
                           len(all_titers_per_serum[serum]),'measurements')


    def normalize_titers(self):
        '''
        convert the titer measurements into the log2 difference between the average
        titer measured between test virus and reference serum and the average
        homologous titer. all measurements relative to sera without homologous titer
        are excluded
        '''
        self.determine_autologous_titers()

        self.titers_normalized = {}
        self.consensus_titers_raw = {}
        self.measurements_per_serum = defaultdict(int)
        for (test, ref), val in self.titers.iteritems():
            if test.upper() in self.node_lookup and ref[0].upper() in self.node_lookup:
                if ref in self.autologous_titers: # use only titers for which estimates of the autologous titer exists
                    self.titers_normalized[(test, ref)] = self.normalize(ref, val)
                    self.consensus_titers_raw[(test, ref)] = np.median(val)
                    self.measurements_per_serum[ref]+=1
                else:
                    pass
                    #print "no homologous titer found:", ref

        self.strain_census()
        print("Normalized titers and restricted to measurements in tree:")
        self.titer_stats()


    def strain_census(self):
        '''
        make lists of reference viruses, test viruses and
        '''
        sera = set()
        ref_strains = set()
        test_strains = set()
        if hasattr(self, 'train_titers'):
            tt = self.train_titers
        else:
            tt = self.titers_normalized

        for test,ref in tt:
            if test.upper() in self.node_lookup and ref[0].upper() in self.node_lookup:
                test_strains.add(test)
                test_strains.add(ref[0])
                sera.add(ref)
                ref_strains.add(ref[0])

        self.sera = list(sera)
        self.ref_strains = list(ref_strains)
        self.test_strains = list(test_strains)


    def titer_stats(self):
        print(" - remaining data set")
        print(' ---', len(self.ref_strains), " reference virues")
        print(' ---', len(self.sera), " sera")
        print(' ---', len(self.test_strains), " test_viruses")
        print(' ---', len(self.titers_normalized), " non-redundant test virus/serum pairs")
        if hasattr(self, 'train_titers'):
            print(' ---', len(self.train_titers), " measurements in training set")


    def subset_to_date(self, date_range):
        # if data is to censored by date, subset the data set and
        # reassign sera, reference strains, and test viruses
        self.train_titers = {key:val for key,val in self.train_titers.iteritems()
                            if self.node_lookup[key[0]].num_date>=date_range[0] and
                               self.node_lookup[key[1][0]].num_date>=date_range[0] and
                               self.node_lookup[key[0]].num_date<date_range[1] and
                               self.node_lookup[key[1][0]].num_date<date_range[1]}
        self.strain_census()
        print("Reduced training data to date range", date_range)
        self.titer_stats()


    def make_training_set(self, training_fraction=1.0, subset_strains=False):
        if training_fraction<1.0: # validation mode, set aside a fraction of measurements to validate the fit
            self.test_titers, self.train_titers = {}, {}
            if subset_strains:    # exclude a fraction of test viruses as opposed to a fraction of the titers
                from random import sample
                tmp = set(self.test_strains)
                tmp.difference_update(self.ref_strains) # don't use references viruses in the set to sample from
                training_strains = sample(tmp, int(training_fraction*len(tmp)))
                for tmpstrain in self.ref_strains:      # add all reference viruses to the training set
                    if tmpstrain not in training_strains:
                        training_strains.append(tmpstrain)
                for key, val in self.titers_normalized.iteritems():
                    if key[0] in training_strains:
                        self.train_titers[key]=val
                    else:
                        self.test_titers[key]=val
            else: # simply use a fraction of all measurements for testing
                for key, val in self.titers_normalized.iteritems():
                    if np.random.uniform()>training_fraction:
                        self.test_titers[key]=val
                    else:
                        self.train_titers[key]=val
        else: # without the need for a test data set, use the entire data set for training
            self.train_titers = self.titers_normalized

        self.strain_census()
        print("Made training data as fraction",training_fraction, "of all measurements")
        self.titer_stats()


    def _train(self, method='nnl1reg',  lam_drop=1.0, lam_pot = 0.5, lam_avi = 3.0):
        '''
        determine the model parameters -- lam_drop, lam_pot, lam_avi are
        the regularization parameters.
        '''
        self.lam_pot = lam_pot
        self.lam_avi = lam_avi
        self.lam_drop = lam_drop
        if len(self.train_titers)==0:
            print('no titers to train')
            self.model_params = np.zeros(self.genetic_params+len(self.sera)+len(self.test_strains))
        else:
            if method=='l1reg':  # l1 regularized fit, no constraint on sign of effect
                self.model_params = self.fit_l1reg()
            elif method=='nnls':  # non-negative least square, not regularized
                self.model_params = self.fit_nnls()
            elif method=='nnl2reg': # non-negative L2 norm regularized fit
                self.model_params = self.fit_nnl2reg()
            elif method=='nnl1reg':  # non-negative fit, branch terms L1 regularized, avidity terms L2 regularized
                self.model_params = self.fit_nnl1reg()

            print('rms deviation on training set=',np.sqrt(self.fit_func()))

        # extract and save the potencies and virus effects. The genetic parameters
        # are subclass specific and need to be process by the subclass
        self.serum_potency = {serum:self.model_params[self.genetic_params+ii]
                              for ii, serum in enumerate(self.sera)}
        self.virus_effect = {strain:self.model_params[self.genetic_params+len(self.sera)+ii]
                             for ii, strain in enumerate(self.test_strains)}


    def fit_func(self):
        return np.mean( (self.titer_dist - np.dot(self.design_matrix, self.model_params))**2 )


    def validate(self, plot=False, cutoff=0.0, validation_set = None):
        '''
        predict titers of the validation set (separate set of test_titers aside previously)
        and compare against known values. If requested by plot=True,
        a figure comparing predicted and measured titers is produced
        '''
        from scipy.stats import linregress, pearsonr
        if validation_set is None:
            validation_set=self.test_titers
        self.validation = {}
        for key, val in validation_set.iteritems():
            pred_titer = self.predict_titer(key[0], key[1], cutoff=cutoff)
            self.validation[key] = (val, pred_titer)

        a = np.array(self.validation.values())
        print ("number of prediction-measurement pairs",a.shape)
        self.abs_error = np.mean(np.abs(a[:,0]-a[:,1]))
        self.rms_error = np.sqrt(np.mean((a[:,0]-a[:,1])**2))
        self.slope, self.intercept, tmpa, tmpb, tmpc = linregress(a[:,0], a[:,1])
        print ("error (abs/rms): ",self.abs_error, self.rms_error)
        print ("slope, intercept:", self.slope, self.intercept)
        print ("pearson correlation:", pearsonr(a[:,0], a[:,1]))

        if plot:
            import matplotlib.pyplot as plt
            import seaborn as sns
            fs=16
            sns.set_style('darkgrid')
            plt.figure()
            ax = plt.subplot(111)
            plt.plot([-1,6], [-1,6], 'k')
            plt.scatter(a[:,0], a[:,1])
            plt.ylabel(r"predicted $\log_2$ distance", fontsize = fs)
            plt.xlabel(r"measured $\log_2$ distance" , fontsize = fs)
            ax.tick_params(axis='both', labelsize=fs)
            plt.text(-2.5,6,'regularization:\nprediction error:', fontsize = fs-2)
            plt.text(1.2,6, str(self.lam_drop)+'/'+str(self.lam_pot)+'/'+str(self.lam_avi)+' (HI/pot/avi)'
                     +'\n'+str(round(self.abs_error, 2))\
                     +'/'+str(round(self.rms_error, 2))+' (abs/rms)', fontsize = fs-2)
            plt.tight_layout()

    def reference_virus_statistic(self):
        '''
        count measurements for every reference virus and serum
        '''
        def dstruct():
            return defaultdict(int)
        self.titer_counts = defaultdict(dstruct)
        for test_vir, (ref_vir, serum) in self.titers_normalized:
            self.titer_counts[ref_vir][serum]+=1


    def compile_titers(self):
        '''
        compiles titer measurements into a json file organized by reference virus
        during visualization, we need the average distance of a test virus from
        a reference virus across sera. hence the hierarchy [ref][test][serum]
        node.clade is used as keys instead of node names
        '''
        def dstruct():
            return defaultdict(dict)
        titer_json = defaultdict(dstruct)

        for key, val in self.titers_normalized.iteritems():
            test_vir, (ref_vir, serum) = key
            test_clade = self.node_lookup[test_vir.upper()].clade
            ref_clade = self.node_lookup[ref_vir.upper()].clade
            titer_json[ref_clade][test_clade][serum] = [np.round(val,TITER_ROUND), np.median(self.titers[key])]

        return titer_json


    def compile_potencies(self):
        '''
        compile a json structure containing potencies for visualization
        we need rapid access to all sera for a given reference virus, hence
        the structure is organized by [ref][serum]
        '''
        potency_json = defaultdict(dict)
        for (ref_vir, serum), val in self.serum_potency.iteritems():
            ref_clade = self.node_lookup[ref_vir.upper()].clade
            potency_json[ref_clade][serum] = np.round(val,TITER_ROUND)

        # add the average potency (weighed by the number of measurements per serum)
        # to the exported data structure
        self.reference_virus_statistic()
        mean_potency = defaultdict(int)
        for (ref_vir, serum), val in self.serum_potency.iteritems():
            mean_potency[ref_vir] += self.titer_counts[ref_vir][serum]*val
        for ref_vir in self.ref_strains:
            ref_clade = self.node_lookup[ref_vir.upper()].clade
            potency_json[ref_clade]['mean_potency'] = 1.0*mean_potency[ref_vir]/np.sum(self.titer_counts[ref_vir].values())

        return potency_json


    def compile_virus_effects(self):
        '''
        compile a json structure containing virus_effects for visualization
        '''
        return {self.node_lookup[test_vir.upper()].clade:np.round(val,TITER_ROUND) for test_vir, val in self.virus_effect.iteritems()}


    ##########################################################################################
    # define fitting routines for different objective functions
    ##########################################################################################
    def fit_l1reg(self):
        '''
        regularize genetic parameters with an l1 norm regardless of sign
        '''
        from cvxopt import matrix, solvers
        n_params = self.design_matrix.shape[1]
        n_genetic = self.genetic_params
        n_sera = len(self.sera)
        n_v = len(self.test_strains)

        # set up the quadratic matrix containing the deviation term (linear xterm below)
        # and the l2-regulatization of the avidities and potencies
        P1 = np.zeros((n_params+n_genetic,n_params+n_genetic))
        P1[:n_params, :n_params] = self.TgT
        for ii in xrange(n_genetic, n_genetic+n_sera):
            P1[ii,ii]+=self.lam_pot
        for ii in xrange(n_genetic+n_sera, n_params):
            P1[ii,ii]+=self.lam_avi
        P = matrix(P1)

        # set up cost for auxillary parameter and the linear cross-term
        q1 = np.zeros(n_params+n_genetic)
        q1[:n_params] = -np.dot( self.titer_dist, self.design_matrix)
        q1[n_params:] = self.lam_drop
        q = matrix(q1)

        # set up linear constraint matrix to regularize the HI parametesr
        h = matrix(np.zeros(2*n_genetic))   # Gw <=h
        G1 = np.zeros((2*n_genetic,n_params+n_genetic))
        G1[:n_genetic, :n_genetic] = -np.eye(n_genetic)
        G1[:n_genetic:, n_params:] = -np.eye(n_genetic)
        G1[n_genetic:, :n_genetic] = np.eye(n_genetic)
        G1[n_genetic:, n_params:] = -np.eye(n_genetic)
        G = matrix(G1)
        W = solvers.qp(P,q,G,h)
        return np.array([x for x in W['x']])[:n_params]


    def fit_nnls(self):
        from scipy.optimize import nnls
        return nnls(self.design_matrix, self.titer_dist)[0]


    def fit_nnl2reg(self):
        from cvxopt import matrix, solvers
        n_params = self.design_matrix.shape[1]
        P = matrix(np.dot(self.design_matrix.T, self.design_matrix) + self.lam_drop*np.eye(n_params))
        q = matrix( -np.dot( self.titer_dist, self.design_matrix))
        h = matrix(np.zeros(n_params)) # Gw <=h
        G = matrix(-np.eye(n_params))
        W = solvers.qp(P,q,G,h)
        return np.array([x for x in W['x']])


    def fit_nnl1reg(self):
        ''' l1 regularization of titer drops with non-negativity constraints'''
        from cvxopt import matrix, solvers
        n_params = self.design_matrix.shape[1]
        n_genetic = self.genetic_params
        n_sera = len(self.sera)
        n_v = len(self.test_strains)

        # set up the quadratic matrix containing the deviation term (linear xterm below)
        # and the l2-regulatization of the avidities and potencies
        P1 = np.zeros((n_params,n_params))
        P1[:n_params, :n_params] = self.TgT
        for ii in xrange(n_genetic, n_genetic+n_sera):
            P1[ii,ii]+=self.lam_pot
        for ii in xrange(n_genetic+n_sera, n_params):
            P1[ii,ii]+=self.lam_avi
        P = matrix(P1)

        # set up cost for auxillary parameter and the linear cross-term
        q1 = np.zeros(n_params)
        q1[:n_params] = -np.dot(self.titer_dist, self.design_matrix)
        q1[:n_genetic] += self.lam_drop
        q = matrix(q1)

        # set up linear constraint matrix to enforce positivity of the
        # dTiters and bounding of dTiter by the auxillary parameter
        h = matrix(np.zeros(n_genetic))     # Gw <=h
        G1 = np.zeros((n_genetic,n_params))
        G1[:n_genetic, :n_genetic] = -np.eye(n_genetic)
        G = matrix(G1)
        W = solvers.qp(P,q,G,h)
        return np.array([x for x in W['x']])[:n_params]

##########################################################################################
# END GENERIC CLASS
##########################################################################################



##########################################################################################
# TREE MODEL
##########################################################################################
class tree_model(titers):
    """
    tree_model extends titers and fits the antigenic differences
    in terms of contributions on the branches of the phylogenetic tree.
    nodes in the tree are decorated with attributes 'dTiter' that contain
    the estimated titer drops across the branch
    """
    def __init__(self,*args, **kwargs):
        super(tree_model, self).__init__(*args, **kwargs)

    def prepare(self, **kwargs):
        self.make_training_set(**kwargs)
        self.find_titer_splits()
        if len(self.train_titers)>1:
            self.make_treegraph()
        else:
            print("TreeModel: no titers in training set")

    def get_path_no_terminals(self, v1, v2):
        '''
        returns the path between two tips in the tree excluding the terminal branches.
        '''
        if v1 in self.node_lookup and v2 in self.node_lookup:
            p1 = [self.node_lookup[v1]]
            p2 = [self.node_lookup[v2]]
            for tmp_p in [p1,p2]:
                while tmp_p[-1].up != self.tree.root:
                    tmp_p.append(tmp_p[-1].up)
                tmp_p.append(self.tree.root)
                tmp_p.reverse()

            for pi, (tmp_v1, tmp_v2) in enumerate(izip(p1,p2)):
                if tmp_v1!=tmp_v2:
                    break
            path = [n for n in p1[pi:] if n.titer_info>1] + [n for n in p2[pi:] if n.titer_info>1]
        else:
            path = None
        return path


    def find_titer_splits(self, criterium=None):
        '''
        walk through the tree, mark all branches that are to be included as model variables
         - no terminals
         - criterium: callable that can be used to exclude branches e.g. if
                      amino acid mutations map to this branch.
        '''
        if criterium is None:
            criterium = lambda x:True
        # flag all branches on the tree with titer_info = True if they lead to strain with titer data
        for leaf in self.tree.get_terminals():
            if leaf.name in self.test_strains:
                leaf.serum = leaf.name in self.ref_strains
                leaf.titer_info = 1
            else:
                leaf.serum, leaf.titer_info=False, 0

        for node in self.tree.get_nonterminals(order='postorder'):
            node.titer_info = sum([c.titer_info for c in node.clades])
            node.serum= False

        # combine sets of branches that span identical sets of titers
        self.titer_split_count = 0  # titer split counter
        self.titer_split_to_branch = defaultdict(list)
        for node in self.tree.find_clades(order='preorder'):
            node.dTiter, node.cTiter, node.constraints = 0, 0, 0
            if node.titer_info>1 and criterium(node):
                node.titer_branch_index = self.titer_split_count
                self.titer_split_to_branch[node.titer_branch_index].append(node)
                # at a bi- or multifurcation, increase the split count and HI index
                # either individual child branches have enough HI info be counted,
                # or the pre-order node iteraction will move towards the root
                if sum([c.titer_info>0 for c in node.clades])>1:
                    self.titer_split_count+=1
                elif node.is_terminal():
                    self.titer_split_count+=1
            else:
                node.titer_branch_index=None

        self.genetic_params = self.titer_split_count
        print ("# of reference strains:",len(self.sera),
               "# of branches with titer constraint", self.titer_split_count)


    def make_treegraph(self):
        '''
        code the path between serum and test virus of each HI measurement into a matrix
        the matrix has dimensions #measurements x #tree branches with HI info
        if the path between test and serum goes through a branch,
        the corresponding matrix element is 1, 0 otherwise
        '''
        tree_graph = []
        titer_dist = []
        weights = []
        # mark HI splits have to have been run before, assigning self.titer_split_count
        n_params = self.titer_split_count + len(self.sera) + len(self.test_strains)
        for (test, ref), val in self.train_titers.iteritems():
            if not np.isnan(val):
                try:
                    if ref[0] in self.node_lookup and test in self.node_lookup:
                        path = self.get_path_no_terminals(test, ref[0])
                        tmp = np.zeros(n_params, dtype=int)
                        # determine branch indices on path
                        branches = np.unique([c.titer_branch_index for c in path
                                                 if c.titer_branch_index is not None])

                        if len(branches): tmp[branches] = 1
                        # add serum effect for heterologous viruses
                        if ref[0]!=test:
                            tmp[self.titer_split_count+self.sera.index(ref)] = 1
                        # add virus effect
                        tmp[self.titer_split_count+len(self.sera)+self.test_strains.index(test)] = 1
                        # append model and fit value to lists tree_graph and titer_dist
                        tree_graph.append(tmp)
                        titer_dist.append(val)
                        weights.append(1.0/(1.0 + self.serum_Kc*self.measurements_per_serum[ref]))
                except:
                    import ipdb; ipdb.set_trace()
                    print(test, ref, "ERROR")

        # convert to numpy arrays and save product of tree graph with its transpose for future use
        self.weights = np.sqrt(weights)
        self.titer_dist =  np.array(titer_dist)*self.weights
        self.design_matrix = (np.array(tree_graph).T*self.weights).T
        self.TgT = np.dot(self.design_matrix.T, self.design_matrix)
        print ("Found", self.design_matrix.shape, "measurements x parameters")

    def train(self,**kwargs):
        self._train(**kwargs)
        for node in self.tree.find_clades(order='postorder'):
            node.dTiter=0 # reset branch properties -- only neede for tree model
            node.cTiter=0
        for titer_split, branches in self.titer_split_to_branch.iteritems():
            likely_branch = branches[np.argmax([b.branch_length for b in branches])]
            likely_branch.dTiter = self.model_params[titer_split]
            likely_branch.constraints = self.design_matrix[:,titer_split].sum()

        # integrate the tree model dTiter into a cumulative antigentic evolution score cTiter
        for node in self.tree.find_clades(order='preorder'):
            if node.up is not None:
                node.cTiter = node.up.cTiter + node.dTiter
            else:
                node.cTiter=0

    def predict_titer(self, virus, serum, cutoff=0.0):
        path = self.get_path_no_terminals(virus,serum[0])
        if path is not None:
            pot = self.serum_potency[serum] if serum in self.serum_potency else 0.0
            avi = self.virus_effect[virus] if virus in self.virus_effect else 0.0
            return avi + pot + np.sum([b.dTiter for b in path if b.dTiter>cutoff])
        else:
            return None



##########################################################################################
# SUBSTITUTION MODEL
##########################################################################################
class substitution_model(titers):
    """
    substitution_model extends titers and implements a model that
    seeks to describe titer differences by sums of contributions of
    substitions separating the test and reference viruses. Sequences
    are assumed to be attached to each terminal node in the tree as
    node.translations
    """
    def __init__(self,*args, **kwargs):
        super(substitution_model, self).__init__(*args, **kwargs)
        self.proteins = self.tree.root.translations.keys()

    def prepare(self, **kwargs):
        self.make_training_set(**kwargs)
        self.determine_relevant_mutations()
        if len(self.train_titers)>1:
            self.make_seqgraph()
        else:
            print('subsitution model: no titers to train')


    def get_mutations(self, strain1, strain2):
        ''' return amino acid mutations between viruses specified by strain names as tuples (HA1, F159S) '''
        if strain1 in self.node_lookup and strain2 in self.node_lookup:
            return self.get_mutations_nodes(self.node_lookup[strain1], self.node_lookup[strain2])
        else:
            return None


    def get_mutations_nodes(self, node1, node2):
        '''
        loops over all translations (listed in self.proteins) and returns a list of
        between as tuples (protein, mutation) e.g. (HA1, 159F)
        '''
        muts = []
        for prot in self.proteins:
            seq1 = node1.translations[prot]
            seq2 = node2.translations[prot]
            muts.extend([(prot, aa1+str(pos+1)+aa2) for pos, (aa1, aa2)
                        in enumerate(izip(seq1, seq2)) if aa1!=aa2])
        return muts


    def determine_relevant_mutations(self, min_count=10):
        # count how often each mutation separates a reference test virus pair
        self.mutation_counter = defaultdict(int)
        for (test, ref), val in self.train_titers.iteritems():
            muts = self.get_mutations(ref[0], test)
            if muts is None:
                continue
            for mut in muts:
                self.mutation_counter[mut]+=1

        # make a list of mutations deemed relevant via frequency thresholds
        relevant_muts = []
        for mut, count in self.mutation_counter.iteritems():
            gene = mut[0]
            pos = int(mut[1][1:-1])-1
            aa1, aa2 = mut[1][0],mut[1][-1]
            if count>min_count:
                relevant_muts.append(mut)

        relevant_muts.sort() # sort by gene
        relevant_muts.sort(key = lambda x:int(x[1][1:-1])) # sort by position in gene
        self.relevant_muts = relevant_muts
        self.genetic_params = len(relevant_muts)


    def make_seqgraph(self, colin_thres = 5):
        '''
        code amino acid differences between sequences into a matrix
        the matrix has dimensions #measurements x #observed mutations
        '''
        seq_graph = []
        titer_dist = []
        weights = []

        n_params = self.genetic_params + len(self.sera) + len(self.test_strains)
        # loop over all measurements and encode the HI model as [0,1,0,1,0,0..] vector:
        # 1-> mutation present, 0 not present, same for serum and virus effects
        for (test, ref), val in self.train_titers.iteritems():
            if not np.isnan(val):
                try:
                    muts = self.get_mutations(ref[0], test)
                    if muts is None:
                        continue
                    tmp = np.zeros(n_params, dtype=int) # zero vector, ones will be filled in
                    # determine branch indices on path
                    mutation_indices = np.unique([self.relevant_muts.index(mut) for mut in muts
                                                  if mut in self.relevant_muts])
                    if len(mutation_indices): tmp[mutation_indices] = 1
                    # add serum effect for heterologous viruses
                    if test!=ref[0]:
                        tmp[self.genetic_params+self.sera.index(ref)] = 1
                    # add virus effect
                    tmp[self.genetic_params+len(self.sera)+self.test_strains.index(test)] = 1
                    # append model and fit value to lists seq_graph and titer_dist
                    seq_graph.append(tmp)
                    titer_dist.append(val)
                    # for each measurment (row in the big matrix), attach weight that accounts for representation of serum
                    weights.append(1.0/(1.0 + self.serum_Kc*self.measurements_per_serum[ref]))
                except:
                    import pdb; pdb.set_trace()
                    print(test, ref, "ERROR")

        # convert to numpy arrays and save product of tree graph with its transpose for future use
        self.weights = np.sqrt(weights)
        self.titer_dist =  np.array(titer_dist)*self.weights
        self.design_matrix = (np.array(seq_graph).T*self.weights).T
        if colin_thres is not None:
            self.collapse_colinear_mutations(colin_thres)
        self.TgT = np.dot(self.design_matrix.T, self.design_matrix)
        print ("Found", self.design_matrix.shape, "measurements x parameters")


    def collapse_colinear_mutations(self, colin_thres):
        '''
        find colinear columns of the design matrix, collapse them into clusters
        '''
        TT = self.design_matrix[:,:self.genetic_params].T
        mutation_clusters = []
        n_measurements = self.design_matrix.shape[0]
        # a greedy algorithm: if column is similar to existing cluster -> merge with cluster, else -> new cluster
        for col, mut in izip(TT, self.relevant_muts):
            col_found = False
            for cluster in mutation_clusters:
                # similarity is defined as number of measurements at whcih the cluster and column differ
                if np.sum(col==cluster[0])>=n_measurements-colin_thres:
                    cluster[1].append(mut)
                    col_found=True
                    print("adding",mut,"to cluster ",cluster[1])
                    break
            if not col_found:
                mutation_clusters.append([col, [mut]])
        print("dimensions of old design matrix",self.design_matrix.shape)
        self.design_matrix = np.hstack((np.array([c[0] for c in mutation_clusters]).T,
                                     self.design_matrix[:,self.genetic_params:]))
        self.genetic_params = len(mutation_clusters)
        # use the first mutation of a cluster to index the effect
        # make a dictionary that maps this effect to the cluster
        self.mutation_clusters = {c[1][0]:c[1] for c in mutation_clusters}
        self.relevant_muts = [c[1][0] for c in mutation_clusters]
        print("dimensions of new design matrix",self.design_matrix.shape)


    def train(self,**kwargs):
        '''
        determine the model parameters. the result will be stored in self.substitution_effect
        '''
        self._train(**kwargs)
        self.substitution_effect={}
        for mi, mut in enumerate(self.relevant_muts):
            self.substitution_effect[mut] = self.model_params[mi]


    def predict_titer(self, virus, serum, cutoff=0.0):
        muts= self.get_mutations(serum[0], virus)
        if muts is not None:
            pot = self.serum_potency[serum] if serum in self.serum_potency else 0.0
            avi = self.virus_effect[virus] if virus in self.virus_effect else 0.0
            return avi + pot\
                + np.sum([self.substitution_effect[mut] for mut in muts
                if (mut in self.substitution_effect and self.substitution_effect[mut]>cutoff)])
        else:
            return None

    def compile_substitution_effects(self, cutoff=1e-4):
        '''
        compile a flat json of substitution effects for visualization, prune mutation without effect
        '''
        return {mut[0]+':'+mut[1]:np.round(val,int(-np.log10(cutoff)))
                for mut, val in self.substitution_effect.iteritems() if val>cutoff}


if __name__=="__main__":
    # test tree model (assumes there is a tree called flu in memory...)
    ttm = tree_model(flu.tree.tree, titer_fname = '../../nextflu2/data/H3N2_HI_titers.txt')
    ttm.prepare(training_fraction=0.8)
    ttm.train(method='nnl1reg')
    ttm.validate(plot=True)

    tsm = substitution_model(flu.tree.tree, titer_fname = '../../nextflu2/data/H3N2_HI_titers.txt')
    tsm.prepare(training_fraction=0.8)
    tsm.train(method='nnl1reg')
    tsm.validate(plot=True)

