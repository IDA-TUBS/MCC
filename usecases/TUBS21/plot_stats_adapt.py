#!/usr/bin/env python3

##############################################################################
# Brief:
# create subplots 
#  every experiment gets its own subplot
#  every variable gets its own y-axis and line
##############################################################################

from argparse import ArgumentParser
import seaborn as sns
import pandas as pd
import csv
import matplotlib.pyplot as plt
import glob
from scipy.stats import ttest_ind

def get_args():
    descr = 'TODO'
    parser = ArgumentParser(description=descr)
    parser.add_argument('--basepath', required=True,
                        help='basepath to experiments')
    parser.add_argument('--vars',  nargs='+',
                        help='each variable gets its own line')
    parser.add_argument('--experiments', nargs='+',
                        help='directory names of all included experiments (each experiment gets its own subplot)')
    parser.add_argument('--labels', nargs='+',
                        help='labels for the experiments')
    parser.add_argument('--kind', type=str, default='swarm',
                        help='type of the plot "box" or "swarm"')
    parser.add_argument('--combine', action='store_true',
                        help='combine results from all solution-*.csv files')
    parser.add_argument('--series', nargs='+',
                        help='directory names of subseries (corresponds to bars in a box group)')
    parser.add_argument('--ylims', nargs='+', type=int, default=None,
                        help='limits the y-axes of the subplots')
    parser.add_argument('--ttest', action='store_true',
                        help='performs t-test and annotates boxes with p-values')
    parser.add_argument('--output', default=None, required=False,
                        help='save plot to given file')
    return parser.parse_args()


def parse_file(filename):
    data = list()
    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')

        last_ops = 0
        last_time = 0
        for row in reader:
            newrow = dict()

            if last_time > 0: # the time of the first solution is not measured
                newrow['Time [s]']   = float(row['time']) - last_time

            newrow['Iterations'] = int(row['iterations'])
            newrow['Combinations']= int(row['combinations'])
            newrow['Operations'] = int(row['rolledback']) + int(row['operations']) - last_ops
            newrow['Complexity'] = int(row['complexity'])
            last_time            = float(row['time'])
            last_ops             = int(row['operations'])

            data.append(newrow)

    return data


def prepare_data(basepath, experiments, labels, series):
    raw_data = list()

    # iterate experiments and parse files
    for exp,label in zip(experiments, labels):
        for serie,var in [s.split('-', 1) for s in series]:
            if args.combine:
                result = []
                for filename in glob.glob('%s/%s/%s/%s/solutions-*.csv' % (basepath, exp, serie, var)):
                    result.extend(parse_file(filename))
            else:
                result = parse_file('%s/%s/%s/%s/solutions.csv' % (basepath, exp, serie, var))

            for r in result:
                r['Increase'] = "%d%%" % (int(serie[-3:]) - 100)
                if var.endswith('fromscratch'):
                    r['Increase'] += " (from scratch)"
                r['Variant'] = "%s" % (label)

            raw_data.extend(result)

    return pd.DataFrame(raw_data)


def create_plot(data, variables, output=None):
    # configure style
    sns.set(style='ticks', context='notebook')

    rows=len(variables)

    f, axes = plt.subplots(rows, 1, sharex=False, figsize=[8, 6])
    row=1
    for var, ax in zip(variables, axes):
        if args.kind == 'box':
            sns.boxplot(x="Variant", y=var, hue="Increase",
                        data=data, notch=False,
                        fliersize=1.5, width=0.85, linewidth=0.8,
                        palette='Paired', ax=ax)
        else:
            sns.swarmplot(x="Variant", y=var, hue="Increase", size=3,
                        data=data, dodge=True, palette="Paired", ax=ax)
        if row > 1:
            ax.legend().set_visible(False)
        else:
            ax.legend(loc='upper left', bbox_to_anchor=(1.05, 1))
        if row < rows:
            ax.set_xlabel('')

        if args.ylims and len(args.ylims) >= row and args.ylims[row-1]:
            ax.set_ylim(bottom=-0.05*args.ylims[row-1], top=args.ylims[row-1])

        if args.ttest:
            # perform t-test for each pair
            pvals = []
            cats = data.Increase.unique()
            for l in args.labels:
                d = data[data.Variant == l]
                for c1, c2 in zip(cats[::2], cats[1::2]):
                    t, p = ttest_ind(list(d[d.Increase == c1][var].dropna()),
                                     list(d[d.Increase == c2][var].dropna()),
                                     equal_var=False)
                    pvals.append(p)

            # annotate
            tmp, y = ax.get_ylim()
            # calculate width of groups
            ticks = ax.get_xticks()
            width = 0.85*(ticks[1] - ticks[0])/3
            for x, pval in zip(ticks, zip(pvals[::3], pvals[1::3], pvals[2::3])):
                for i, p in zip([-1, 0, 1], pval):
                    ax.annotate('p={:.3f}'.format(p),
                                xy=(x+i*width, y),
                                xytext=(0, 0),
                                textcoords="offset points",
                                ha='center', va='center')

        row += 1

    sns.despine()
    if output:
        plt.savefig(output, bbox_inches='tight')
    else:
        plt.show()


if __name__ == '__main__':

    args = get_args()
    assert len(args.experiments) == len(args.labels)

    data = prepare_data(args.basepath, args.experiments, args.labels, args.series)

    create_plot(data, args.vars, output=args.output)
