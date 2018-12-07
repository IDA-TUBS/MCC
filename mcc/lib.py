"""
Description
-----------

Implements variants of the MCC by composing cross-layer models, analysis engines, and steps.

:Authors:
    - Johannes Schlatow

"""
from mcc.model import *
from mcc.framework import *
from mcc.analyses import *
from mcc.importexport import *

from mcc.model_extractor import *

class BaseModelQuery:
    """ Stores existing component architecture and corresponding inputs.
    """

    def __init__(self):
        # store queries (filenames and graphs) by name
        self._queries    = dict()

        # store component instances and mapping from components to corresponding queries
        self._components = None

    def _merge(self, components, query):
        if self._components is not None:
            # copy 'query' param from _components to components
            for c in _components.graph.nodes():
                for cnew in components.graph.nodes():
                    if c.identifier() == cnew.identifier():
                        q = self._components._get_param_value('query', c)
                        components._set_param_value('query', cnew, q)

        # replace _components
        self._components = components

        # new components are mapped to query
        for c in self._components.graph.nodes():
            if self._components._get_param_value('query', c) is None:
                self._components._set_param_value('query', c, query)

    def insert(self, name, query_graph, comp_inst, filename=None):
        # insert name and query graph
        self._queries[name] = { 'filename' : filename,
                                'graph'    : query_graph }

        # merge comp_inst into current components
        assert len(comp_inst.graph.nodes()) > 0, "inserting empty graph"
        self._merge(comp_inst, name)

    def base_arch(self):
        # For each subsystem, return an object that aggregates
        # the existing functions and components.

        subsystems = dict()

        # aggregate components per subsystem
        for c in self._components.graph.nodes():
            name = self._components._get_param_value('mapping', c).name()
            if name not in subsystems:
                subsystems[name] = set()
            subsystems[name].add(c)

        arch = set()
        for name, comps in subsystems.items():
            arch.add(BaseChild('base', name, comps, self._components.graph.subgraph(comps)))

        return arch

    def instances(self, subsystem):
        # return instances of given subsystem
        instances = set()
        for c in self._components.graph.nodes():
            if subsystem == self._components._get_param_value('mapping', c).name():
                instances.add(c)

        return instances

class MccBase:
    """ MCC base class. Implements helper functions for common transformation steps.
    """

    def __init__(self, repo):
        """
        Args:
            :param repo: component and contract repository
        """
        self.repo = repo

    def _complete_mapping(self, model, layer):
        # inherit mapping from all neighbours (excluding static platform components)
        model.add_step(InheritFromBothStep(layer, 'mapping', engines={StaticEngine(layer)}))

    def _select_components(self, model, slayer, dlayer):
        """ Selects components for nodes in source layer and transforms into target layer.

        Args:
            :param model: cross-layer model
            :type  model: :class:`mcc.framework.Registry`
            :param slayer: source layer
            :param dlayer: target layer
        """
        fc = model.by_name[slayer]
        ca = model.by_name[dlayer]

        ce   = ComponentEngine(fc, self.repo)
        rtee = RteEngine(fc)
        spe  = SpecEngine(fc)

        # Map operation is the first when selecting components
        comps = Map(ce, 'component')
        comps.register_ae(rtee)                     #   consider rte requirements
        comps.register_ae(spe)                      #   consider spec requirements

        # check platform compatibility
        pf_compat = NodeStep(comps)                  # get components from repo
        assign = pf_compat.add_operation(Assign(ce, 'component')) # choose component
        check = pf_compat.add_operation(Check(rtee, name='RTE requirements')) # check rte requirements
        check.register_ae(spe)                       # check spec requirements
        model.add_step(pf_compat)

        # check dependencies
        model.add_step(NodeStep(Check(DependencyEngine(fc), name='dependencies')))

        # select pattern (dummy step, nothing happening here)
        pe = PatternEngine(fc)
        model.add_step(MapAssignNodeStep(pe, 'pattern'))

        # sanity check and transform
        transform = NodeStep(Check(pe, name='pattern'))
        transform.add_operation(Transform(pe, ca, 'pattern'))
        model.add_step(transform)

        # select service connection and fix constraints
        #  remark: for the moment, we assume there is only one possible connection left
        se = ServiceEngine(fc, ca)
        connect = EdgeStep(Check(se, name='connect'))
        connect.add_operation(Map(se, name='connect'))
        connect.add_operation(Assign(se, name='connect'))
        connect.add_operation(Transform(se, ca, name='connect'))
        model.add_step(connect)

        # copy mapping from slayer to dlayer
        model.add_step(CopyMappingStep(fc, ca))

        self._complete_mapping(model, ca)

        # check mapping
        model.add_step(NodeStep(Check(MappingEngine(ca), name='platform mapping is complete')))

        # TODO (?) check that connections satisfy functional dependencies

    def _insert_protocolstacks(self, model, slayer, dlayer):
        """ Inserts protocol stacks for edges in source layer and transforms into target layer.

        Args:
            :param model: cross-layer model
            :type  model: :class:`mcc.framework.Registry`
            :param slayer: source layer
            :param dlayer: target layer
        """

        slayer = model.by_name[slayer]
        dlayer = model.by_name[dlayer]

        # select protocol stacks
        pse = ProtocolStackEngine(slayer, self.repo)
        select = EdgeStep(Map(pse))
        select.add_operation(Assign(pse))

        # select pattern (if composite)
        pe = PatternEngine(slayer, source_param='protocolstack')
        select.add_operation(Map(pe))
        select.add_operation(Assign(pe))
        model.add_step(select)

        # copy nodes
        model.add_step(CopyNodeStep(slayer, dlayer))
        model.add_step(CopyMappingStep(slayer, dlayer))

        # copy or transform edges
        model.add_step(EdgeStep(Transform(pe, dlayer)))
        model.add_step(CopyServicesStep(slayer, dlayer))

        # derive mapping
        self._complete_mapping(model, dlayer)

        # check that service dependencies are satisfied and connections are local
        model.add_step(EdgeStep(Check(ComponentDependencyEngine(dlayer), name='service dependencies')))
        model.add_step(NodeStep(Check(ComponentDependencyEngine(dlayer), name='service dependencies')))

    def _insert_muxers(self, model, slayer, dlayer):
        """ Inserts multiplexers for edges in source layer and transforms into target layer.

        Args:
            :param model: cross-layer model
            :type  model: :class:`mcc.framework.Registry`
            :param slayer: source layer
            :param dlayer: target layer
        """

        slayer = model.by_name[slayer]
        dlayer = model.by_name[dlayer]

        # select muxers and transform
        me = MuxerEngine(slayer, self.repo)
        select = NodeStep(Map(me))
        select.add_operation(Assign(me))
        select.add_operation(Transform(me, dlayer))
        model.add_step(select)

        # adapt edges to inserted muxers and transform
        adapt_edges = EdgeStep(Map(me))
        adapt_edges.add_operation(Assign(me))
        adapt_edges.add_operation(Transform(me, dlayer))
        model.add_step(adapt_edges)

        # derive mapping
        self._complete_mapping(model, dlayer)

        # check that service dependencies are satisfied and connections are local
        model.add_step(NodeStep(Check(ComponentDependencyEngine(dlayer), name='service dependencies')))

    def _insert_proxies(self, model, slayer, dlayer):
        """ Inserts proxies for edges in source layer and transforms into target layer.

        Args:
            :param model: cross-layer model
            :type  model: :class:`mcc.framework.Registry`
            :param slayer: source layer
            :param dlayer: target layer
        """

        fa = model.by_name[slayer]
        fc = model.by_name[dlayer]

        re = ReachabilityEngine(fa, fc, model.platform)

        # decide on reachability
        reachability = EdgeStep(Map(re, 'carrier'))         # map edges to carrier
        reachability.add_operation(Assign(re, 'carrier'))   # choose communication carrier
        model.add_step(reachability)

        # copy nodes to comm arch
        model.add_step(CopyNodeStep(fa, fc))
        model.add_step(CopyMappingStep(fa, fc))

        # perform arc split
        model.add_step(EdgeStep(Transform(re, fc, 'arc split')))

    def _merge_components(self, model, slayer, dlayer, factory, pf_model):
        """ Merge components into component instantiations.

        Args:
            :param model: cross-layer model
            :type  model: :class:`mcc.framework.Registry`
            :param slayer: source layer
            :param dlayer: target layer
            :param factory: instance factory
            :type  factory: :class:`mcc.model.InstanceFactory`
        """

        ca = model.by_name[slayer]
        ci = model.by_name[dlayer]

        ie = InstantiationEngine(ca, ci, factory)

        instantiate = NodeStep(Map(ie, 'instantiate'))
        instantiate.add_operation(Assign(ie, 'instantiate'))
        instantiate.add_operation(Transform(ie, ci, 'instantiate'))
        model.add_step(instantiate)
        model.add_step(EdgeStep(Transform(ie, ci, 'copy edges')))

        # check singleton (per PfComponent)
        se = SingletonEngine(ci, pf_model)
        model.add_step(NodeStep(Check(se, 'check singleton and cardinality')))

    def _assign_resources(self, model, layer):
        layer = model.by_name[layer]

        # TODO actually assign resources as specified in repo
        #      currently, we just take the resources as specified but check
        #      whether they exceed any threshold
        ce = QuantumEngine(layer, name='caps')

        resources = NodeStep(Check(ce, 'caps'))

        re = QuantumEngine(layer, name='ram')
        resources.add_operation(Check(re, 'ram'))

        model.add_step(resources)


class SimpleMcc(MccBase):
    """ Composes MCC for Genode systems. Only considers functional requirements.
    """

    def __init__(self, repo, test_backtracking=False):
        MccBase.__init__(self, repo)
        self._test_backtracking = test_backtracking

    def insert_random_backtracking_engine(self, model, failure_rate=0.0):
        # TODO idea for better testing: only fail if there are candidates left for any assign in the dependency tree
        #      if we then set failure_rate to 1.0, we can traverse the entire search space
        assert(0 <= failure_rate <= 1.0)

        source_layer = model.steps[len(model.steps)-1].source_layer;
        # target_layer = self.ste[r-1].target_layer;
        bt = BacktrackingTestEngine(source_layer, 'mapping', model.decision_graph(), failure_rate, fail_once=False)
        model.steps.append(NodeStep(Check(bt, 'BackTrackingTest')))

    def search_config(self, pf_model, system, base=None, outpath=None, with_da=False, da_path=None):
        """ Searches a system configuration for the given query.

        Args:
            :param base: base model (existing functions/components)
            :param base: BaseModelQuery object
            :param platform: platform parser
            :type  platform: parser object
            :param system: system configuruation parser
            :type  system: parser object
            :param outpath: output path/prefix
            :type  outpath: str
        """

        # check function/composite/component references, compatibility and routes in system and subsystems

        # 2) we create a new system model
        model = SystemModel(self.repo, pf_model, dotpath=outpath)

        # 3) create query model
        query_model = FuncArchQuery(system)

        # output query model
        if outpath is not None:
            query_model.write_dot(outpath+"query_graph.dot")
            pf_model.write_dot(outpath+"platform.dot")

        # 4a) create system model from query model and base
        model.from_query(query_model, base)

        # 4b) solve function dependencies (if already known)
        #      currently, we assume that all functional dependencies
        #      are predefined in the query
        model.connect_functions()

        # remark: 'mapping' is already fixed in func_arch
        #  we thus assign just assign nodes to platform components as queried
        fa = model.by_name['func_arch']
        qe = QueryEngine(fa)
        model.add_step(NodeStep(Assign(qe, 'query')))

        # solve reachability and transform into comm_arch
        self._insert_proxies(model, slayer='func_arch', dlayer='comm_arch')

        # select components and transform into comp_arch
        self._select_components(model, slayer='comm_arch', dlayer='comp_arch-pre1')

        # TODO test case for protocol stack insertion
        self._insert_protocolstacks(model, slayer='comp_arch-pre1', dlayer='comp_arch-pre2')

        # insert muxers (if connections present and muxer is available)
        # TODO test case for replication
        self._insert_muxers(model, slayer='comp_arch-pre2', dlayer='comp_arch')

        # create instance factory and insert existing instance from base
        instance_factory = InstanceFactory()

        if base is not None:
            # for each subsystem insert existing instances into factory
            for pfc in pf_model.platform_graph.nodes():
                instance_factory.insert_existing_instances(pfc.name(), base.instances(pfc.name()))


        # implement transformation/merge into component instantiation
        self._merge_components(model, slayer='comp_arch', dlayer='comp_inst',
                factory=instance_factory, pf_model=pf_model)

        # assign and check resource consumptions (RAM, caps)
        self._assign_resources(model, layer='comp_inst')

        # insert backtracking engine for testing (random rejection of candidates)
        if self._test_backtracking:
            self.insert_random_backtracking_engine(model, 0.05)

        model.print_steps()
        if outpath is not None:
            model.write_dot(outpath+'mcc.dot')

        if with_da:
            from mcc import extern

            if da_path is None:
                da_path = outpath

            da_engine = extern.DependencyAnalysisEngine(model, model.by_order, outpath+'model.pickle', outpath+'query.xml', da_path+'response.xml')
            da_step = NodeStep(BatchMap(da_engine))
            da_step.add_operation(BatchAssign(da_engine))
            model.add_step_unsafe(da_step)

        try:
            model.execute()
        except Exception as e:
            print(e)
            model_extractor = ModelExtractor(model.by_name)
            model_extractor.write_xml(outpath+'model-error.xml')
            raise e

        model.write_analysis_engine_dependency_graph(outpath+'ae_dep_graph.dot')
        model.decision_graph().write_dot(outpath+'dec_graph.dot')

        model_extractor = ModelExtractor(model.by_name)
        model_extractor.write_xml(outpath+'model.xml')

        # FIXME decision graph extractor does not work
        decision_extractor = DecisionGraphExtractor(model.decision_graph())
#        decision_extractor.write_xml(outpath+'dec_graph.xml')

        return (query_model, model)
