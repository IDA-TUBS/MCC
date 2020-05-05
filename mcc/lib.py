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
from mcc.simulation import *
from mcc.complex_analyses import *
from mcc.importexport import *

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
                        q = self._components.untracked_get_param_value('query', c)
                        components.untracked_set_param_value('query', cnew, q)

        # replace _components
        self._components = components

        # new components are mapped to query
        for c in self._components.graph.nodes():
            if not self._components.untracked_isset_param_value('query', c):
                self._components.untracked_set_param_value('query', c, query)

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
            name = self._components.untracked_get_param_value('mapping', c).name()
            if name not in subsystems:
                subsystems[name] = set()
            subsystems[name].add(c)

        arch = set()
        for name, comps in subsystems.items():
            instances = [c.untracked_obj() for c in comps]
            arch.add(BaseChild('base', name, instances, self._components.graph.subgraph(comps, {'mapping'})))

        return arch

    def instances(self, subsystem):
        # return instances of given subsystem
        instances = set()
        for c in self._components.graph.nodes():
            if subsystem == self._components.untracked_get_param_value('mapping', c).name():
                inst = c.untracked_obj()
                inst._static = True
                instances.add(inst)

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

    def _complete_mapping(self, model, layer, source_param='mapping'):
        # inherit mapping from all neighbours (excluding static platform components)
        model.add_step(InheritFromBothStep(layer,
                                           param=source_param,
                                           target_param='mapping',
                                           engines={StaticEngine(layer)}))

    def _map_functions(self, model, layer):
        fa = model.by_name[layer]

        me = MappingEngine(fa, model.repo, model.platform, cost_sensitive=True)
        cpme = CPMappingEngine(fa, model.repo, model.platform)

        pfmap = NodeStep(Map(me, 'map functions'))
        pfmap.add_operation(BatchAssign(cpme, 'map functions'))
        pfmap.add_operation(BatchCheck(me, 'map functions'))
        model.add_step(pfmap)

    def _connect_functions(self, model, slayer, dlayer):
        fq = model.by_name[slayer]
        fa = model.by_name[dlayer]

        fe = FunctionEngine(fq, fa, model.repo)
        deps = NodeStep(Map(fe, 'dependencies'))
        deps.add_operation(Assign(fe, 'dependencies'))
        deps.add_operation(BatchTransform(fe, fa, 'dependencies'))

        model.add_step(deps)
        model.add_step(CopyEdgeStep(fq, fa, {'service'}))

    def _map_and_connect_functions(self, model, slayer, dlayer):
        fq = model.by_name[slayer]
        fa = model.by_name[dlayer]

        me = MappingEngine(fq, model.repo, model.platform, cost_sensitive=True)
        #cpme = CPMappingEngine(fq, model.repo, model.platform)
        fe = FunctionEngine(fq, fa, model.repo)

        step = NodeStep(              Map(fe, 'dependencies'))
        step.add_operation(           Map(me, 'map functions'))
        step.add_operation(   BatchAssign(me, 'map functions'))
        step.add_operation(    BatchCheck(me, 'map functions'))
        step.add_operation(        Assign(fe, 'dependencies'))
        step.add_operation(BatchTransform(fe, fa, 'dependencies'))

        model.add_step(step)

        model.add_step(CopyEdgeStep(fq, fa, {'service'}))

    def _select_components(self, model, slayer, dlayer, envmodel):
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
        pe = PatternEngine(fc, ca)
        epe = EnvPatternEngine(fc, envmodel)
        patterns = Map(pe, 'pattern')
        patterns.register_ae(epe)
        patstep = NodeStep(patterns)
        patstep.add_operation(Assign(pe, 'pattern'))
        # sanity check and transform
        patstep.add_operation(    Check(pe, name='pattern'))
        patstep.add_operation(Transform(pe, ca, 'pattern'))
        model.add_step(patstep)

        # select service connection and fix constraints
        #  remark: for the moment, we assume there is only one possible connection left
        se = ServiceEngine(fc, ca)
        connect = EdgeStep(Check(se, name='connect'))
        connect.add_operation(Map(se, name='connect'))
        connect.add_operation(Assign(se, name='connect'))
        connect.add_operation(Transform(se, ca, name='connect'))
        model.add_step(connect)

#        # check network bandwith
#        model.add_step_unsafe(NodeStep(BatchCheck(NetworkEngine(fc), name='network bandwith')))

        # copy mapping from slayer to dlayer

        self._complete_mapping(model, ca, source_param='mapping')

        # check mapping
        model.add_step(NodeStep(Check(MappingEngine(ca, model.repo, model.platform), name='platform mapping is complete')))

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
        pe = PatternEngine(slayer, dlayer, source_param='protocolstack')
        select.add_operation(Map(pe))
        select.add_operation(Assign(pe))
        model.add_step(select)

        # copy nodes
        model.add_step(CopyNodeStep(slayer, dlayer, {'mapping', 'pattern-config'}))

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
        me = MuxerEngine(slayer, dlayer, self.repo)
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
        model.add_step(CopyNodeStep(fa, fc, {'mapping'}))

        # perform arc split
        model.add_step(EdgeStep(BatchTransform(re, fc, 'arc split')))

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

        ie = InstantiationEngine(ca, ci, factory, 'tmp-mapping')

        instantiate = NodeStep(Map(ie, 'instantiate'))
        instantiate.add_operation(Assign(ie, 'instantiate'))
        instantiate.add_operation(Transform(ie, ci, 'instantiate'))
        model.add_step(instantiate)
        connect = EdgeStep(Map(ie, 'copy edges'))
        connect.add_operation(Assign(ie, 'copy edges'))
        connect.add_operation(Transform(ie, ci, 'copy edges'))
        model.add_step(connect)

        ce = CoprocEngine(ci, pf_model, 'tmp-mapping')
        coproc = NodeStep(      Map(ce, 'coproc'))
        coproc.add_operation(Assign(ce, 'coproc'))
        model.add_step(coproc)

        # check singleton (per PfComponent)
        se = SingletonEngine(ci, pf_model)
        model.add_step(NodeStep(Check(se, 'check singleton and cardinality')))

    def _assign_resources(self, model, layer):
        layer = model.by_name[layer]

        # TODO actually assign resources as specified in repo
        #      currently, we just take the resources as specified but check
        #      whether they exceed any threshold
        ce = QuantumEngine(layer, name='caps')

        resources = NodeStep(BatchCheck(ce, 'caps'))

        re = QuantumEngine(layer, name='ram')
        resources.add_operation(BatchCheck(re, 'ram'))

        model.add_step(resources)

    def _reliability_check(self, model, layer, constrmodel):
        """ perform reliability checks
        """

        layer = model.by_name[layer]
        re   = ReliabilityEngine(layer, model.by_order[1:], constrmodel)
        model.add_step_unsafe(NodeStep(BatchCheck(re, 'check reliability')))

    def _assign_affinity(self, model, layer):
        layer = model.by_name[layer]

        ae = AffinityEngine(layer)

        step = NodeStep(      Map(ae, 'set affinity'))
        step.add_operation(Assign(ae, 'set affinity'))

        model.add_step(step)

    def _timing_model(self, model, pf_model, slayer, dlayer, constrmodel):
        """ Build taskgraph layer and perform timing checks
        """

        slayer = model.by_name[slayer]
        tg     = model.by_name[dlayer]

        core = TasksCoreEngine(slayer)
        rpc  = TasksRPCEngine(slayer)
        ae   = TaskgraphEngine(slayer, tg)

        tasks = NodeStep(         Map(core, 'get coretasks'))
        tasks.add_operation(   Assign(core, 'get coretasks'))
        tasks.add_operation(      Map(rpc, 'get rpctasks'))
        tasks.add_operation(   Assign(rpc, 'get rpctasks'))
        tasks.add_operation(      Map(ae, 'build taskgraph'))
        tasks.add_operation(   Assign(ae, 'build taskgraph'))
        tasks.add_operation(    Check(ae, 'build taskgraph'))
        tasks.add_operation(Transform(ae, tg, 'build taskgraph'))
        model.add_step(tasks)

        con = EdgeStep(Map(ae, 'connect tasks'))
        con.add_operation(Assign(ae, 'connect tasks'))
        con.add_operation(Transform(ae, tg, 'connect tasks'))
        model.add_step(con)


        # assign event model to interrupt tasks
        acte = ActivationEngine(tg)
        activation = NodeStep(       Map(acte, 'activation pattern'))
        activation.add_operation(    Assign(acte, 'activation patterns'))
        model.add_step(activation)

        # assign priorities
        pe = PriorityEngine(slayer, taskgraph=tg, platform=pf_model)
        prios = NodeStep(      BatchMap(pe, 'assign priorities'))
        prios.add_operation(BatchAssign(pe, 'assign priorities'))
        model.add_step_unsafe(prios)

        # assign WCETs
        we = WcetEngine(tg)
        wcets = NodeStep(       Map(we, 'WCETs'))
        wcets.add_operation(    Assign(we, 'WCETs'))
        model.add_step(wcets)

    def _timing_check(self, model, slayer, dlayer, constrmodel, ae):

        slayer = model.by_name[slayer]
        tg     = model.by_name[dlayer]

        # perform CPA
        pycpa = CPAEngine(tg, slayer, model.by_order[1:], constrmodel)
        check = BatchCheck(pycpa, 'CPA')
        if ae:
            check.register_ae(ae)
        model.add_step(NodeStep(check))

class SimpleMcc(MccBase):
    """ Composes MCC for Genode systems. Only considers functional requirements.
    """

    def __init__(self, repo, test_backtracking=False, chronologicaltracking=False, test_adaptation=False):
        assert test_backtracking == False or test_adaptation == False
        assert chronologicaltracking == False or test_adaptation == False

        MccBase.__init__(self, repo)
        self._test_backtracking = test_backtracking
        self._test_adaptation   = test_adaptation
        self._nonchronological  = not chronologicaltracking

    def search_config(self, pf_model, system, base=None, outpath=None, with_da=False, da_path=None, dot_mcc=False,
            dot_ae=False, dot_layer=False, envmodel=None, constrmodel=None):
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
        model = SystemModel(self.repo, pf_model, dotpath=outpath if dot_layer else None)

        # 3) create query model
        query_model = FuncArchQuery(system)

        # 4a) create system model from query model and base
        model.from_query(query_model, 'func_query', base)

        # parse constraints
        if constrmodel is not None:
            constrmodel.parse(model)

        self._map_and_connect_functions(model, 'func_query', 'func_arch')

#        self._map_functions(model, 'func_query')
#        self._connect_functions(model, 'func_query', 'func_arch')

        # solve reachability and transform into comm_arch
        self._insert_proxies(model, slayer='func_arch', dlayer='comm_arch')

        # select components and transform into comp_arch
        self._select_components(model, slayer='comm_arch', dlayer='comp_arch-pre1', envmodel=envmodel)

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

        # do not do scheduling stuff for base model
        if base is not None:
            # assign affinity
            self._assign_affinity(model, layer='comp_inst')

            self._timing_model(model, pf_model, slayer='comp_inst',
                                                dlayer='task_graph',
                                                constrmodel=constrmodel)

            sim = None
            if self._test_backtracking:
                sim = BacktrackingSimulation(model.by_name['task_graph'], model, outpath=outpath)

            if constrmodel is not None:
                self._reliability_check(model, layer='comp_inst', constrmodel=constrmodel)
                self._timing_check(model, slayer='comp_inst', dlayer='task_graph',
                                   constrmodel=constrmodel, ae=sim)

            if self._test_adaptation:
                sim = AdaptationSimulation(model.by_name['task_graph'], model, factor=self._test_adaptation, outpath=outpath)
                model.add_step(NodeStep(BatchCheck(sim)))

#        model.print_steps()
        if outpath is not None and dot_mcc:
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
            model.execute(outpath, nonchronological=self._nonchronological)
            decision_graph = model.decision_graph

        except Exception as e:
            if sim:
                sim.write_stats(outpath[:outpath.rfind('/')] + '/solutions.csv')

            print(e)
            export = PickleExporter(model)
            export.write(outpath+'model-error.pickle')
            raise e

        if outpath is not None and dot_ae:
            model.write_analysis_engine_dependency_graph(outpath+'ae_dep_graph.dot')

        export = PickleExporter(model)
        export.write(outpath+'model.pickle')

        return (query_model, model)
