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

class MccBase:
    """ MCC base class. Implements helper functions for common transformation steps.
    """

    def __init__(self, repo):
        """
        Args:
            :param repo: component and contract repository
        """
        self.repo = repo

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

        model.add_step(CopyMappingStep(fc, ca))
        model.add_step(InheritFromBothStep(ca, 'mapping'))

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
        model.add_step(InheritFromBothStep(dlayer, 'mapping'))

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

        # select muxers
        me = MuxerEngine(slayer, self.repo)
        select = NodeStep(Map(me))
        select.add_operation(Assign(me))
        model.add_step(select)

        # TODO continue here

        # copy & transform
        model.add_step(CopyNodeStep(slayer, dlayer))
        model.add_step(CopyMappingStep(slayer, dlayer))
        model.add_step(CopyEdgeStep(slayer, dlayer))

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



class SimpleMcc(MccBase):
    """ Composes MCC for Genode systems. Only considers functional requirements.
    """

    def __init__(self, repo):
        MccBase.__init__(self, repo)

    def search_config(self, platform_xml, system_xml, xsd_file=None, outpath=None):
        """ Searches a system configuration for the given query.

        Args:
            :param platform_xml: filename containing platform specification
            :type  platform_xml: str
            :param system_xml: filename containing abstract system configuruation
            :type  system_xml: str
            :param xsd_file: XSD filename for subsystem_xml
            :type  xsd_file: str
            :param outpath: output path/prefix
            :type  outpath: str
        """

        # check function/composite/component references, compatibility and routes in system and subsystems

        # 1) we parse the platform model
        pf_model = SimplePlatformModel(PlatformParser(platform_xml, xsd_file))

        # 2) we create a new system model
        model = SystemModel(self.repo, pf_model, dotpath=outpath)

        # 3) create query model 
        query_model = FuncArchQuery(SystemParser(system_xml, xsd_file))

        # output query model
        if outpath is not None:
            query_model.write_dot(outpath+"query_graph.dot")
            pf_model.write_dot(outpath+"platform.dot")

        # 4a) create system model from query model
        model.from_query(query_model)

#        # 4b) solve function dependencies (if already known)
#        self.model.connect_functions()

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

        # TODO test case for muxer insertion
#        self._insert_muxers(slayer='comp_arch-pre2', dlayer='comp_arch')

        # TODO implement transformation/merge into component instantiation

        # TODO implement backtracking

        model.print_steps()
        if outpath is not None:
            model.write_dot(outpath+'mcc.dot')
        model.execute()

        export = PickleExporter(model, { model.by_name['func_arch'] : { 'reads' : ['mapping', 'service'] },
                                         model.by_name['comm_arch'] : { 'reads' : ['mapping', 'service'] } })
        export.write(outpath+'func_arch.gpickle')

        model = SystemModel(self.repo, pf_model, dotpath=outpath)

        importer = PickleImporter(model)
        importer.read(outpath+'func_arch.gpickle')

        model._output_layer(model.by_name['func_arch'], 'asdf')
        model._output_layer(model.by_name['comm_arch'], 'asdf')

        return True
