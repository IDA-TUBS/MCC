#!/usr/bin/env python

import logging
import argparse
from mcc import parser as cfgparser
from mcc import model
from mcc import lib
from mcc.configurator import GenodeConfigurator

parser = argparse.ArgumentParser(description='Check config model XML.')
parser.add_argument('files', metavar='xml_file', type=str, nargs='+',
        help='XML files to be processed (<system>)')
parser.add_argument('--base', type=str, required=True,
        help='Base system specification')
parser.add_argument('--schema', type=str, default="XMLCCC.xsd",
        help='XML Schema Definition (xsd)')
parser.add_argument('--platform', type=str, default=None,
        help='XML file with platform specification (<platform>)')
#parser.add_argument('--repos', type=str, default=list, nargs='*',
#        help='XML files with contract repository (<repository>)')
parser.add_argument('--dotpath', type=str,
        help='Write graphs to DOT files in this path.')
parser.add_argument('--config_xsd', type=str, default='genode_xsd/config.xsd',
        help='Config XSD schema.')
parser.add_argument('--dependency_analysis', action='store_true')

args = parser.parse_args()

################
# main section #
################

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)

    # take platform from the first file if not overridden with --platform
    pffile = args.platform
    if pffile is None:
        if args.base is None:
            pffile = args.files[0]
        else:
            pffile = args.base

    pf = cfgparser.PlatformParser(pffile, args.schema)
    pf_model = model.SimplePlatformModel(pf)

    # try to create repositories from given files
    repos = list()
    if args.base is not None:
        repo = cfgparser.Repository(args.base, args.schema)
        repos.append(repo)

    for repofile in args.files:
        try:
            repo = cfgparser.Repository(repofile, args.schema)
            repos.append(repo)
        except:
            continue

    cfg = cfgparser.AggregateRepository(repos)
    mcc = lib.SimpleMcc(repo=cfg, test_backtracking=False)

    base = lib.BaseModelQuery()

    basesys   = cfgparser.SystemParser(args.base, args.schema)
    query, basemodel = mcc.search_config(pf_model, basesys,
                           outpath=args.dotpath+'-'+basesys.name()+'-',
                           with_da=False)

    # store basemodel in BaseModelQuery
    base.insert(name=basesys.name(),
                query_graph=query,
                comp_inst=basemodel.by_name['comp_inst'],
                filename=args.base)

    sys = cfgparser.AggregateSystemParser()
    for sysfile in args.files:
        sys.append(cfgparser.SystemParser(sysfile, args.schema))

    try:
        query, model = mcc.search_config(pf_model, sys, base,
                                  outpath=args.dotpath+'-'+sys.name()+'-',
                                  with_da=args.dependency_analysis)

        # generate <config> from model
        configurator = GenodeConfigurator(args.dotpath+'-'+sys.name()+'-', pf_model,
                                          args.config_xsd)
        configurator.create_configs(model, layer_name='comp_inst')

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(e)

