#!/usr/bin/env python3

##############################################################################
# Brief:
# create subplots for iterations, operations and time
#  every subplot shows two boxplots (chrono/nonchrono) for each experiment
##############################################################################

from argparse import ArgumentParser
import seaborn as sns
import pandas as pd
import csv
import matplotlib.pyplot as plt

def get_args():
    descr = 'TODO'
    parser = ArgumentParser(description=descr)
    parser.add_argument('--basepath', required=True,
                        help='basepath to experiments')
    parser.add_argument('--vars',  nargs='+',
                        help='each variable gets its own subplot')
    parser.add_argument('--experiments', nargs='+',
                        help='directory names of all included experiments')
    parser.add_argument('--labels', nargs='+',
                        help='labels for the experiments')
    parser.add_argument('--output', default=None, required=False,
                        help='save plot to given file')
    parser.add_argument('--ylims', nargs='+', type=int,
                        help='limits the y-axes of the subplots')
    return parser.parse_args()


def parse_file(filename):
    data = list()
    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')

        for row in reader:
            newrow = dict()
            newrow['Total Time [s]'] = float(row['time'])
            newrow['Iterations']     = int(row['iterations'])
            newrow['Operations']     = int(row['operations'])
            newrow['run']            = int(row['run'])
            data.append(newrow)

    return data


def prepare_data(basepath, experiments, labels):

    # iterate experiments and parse files
    raw_data = list()
    for exp,label in zip(experiments, labels):
        chrono    = parse_file('%s/%s/test/chrono/results.csv'    % (basepath, exp))
        nonchrono = parse_file('%s/%s/test/nonchrono/results.csv' % (basepath, exp))

        # assert that both files have the same sample size
        if len(chrono) != len(nonchrono):
            print("WARNING: different number of samples in %s: %d vs %d" % (exp, len(chrono), len(nonchrono)))


        for r in chrono:
            r['search']   = 'chronological'
            r['Variant'] = label

        for r in nonchrono:
            r['search'] = 'non-chronological'
            r['Variant'] = label

        raw_data.extend(chrono + nonchrono)

    return pd.DataFrame(raw_data)


def create_plot(data, variables, output=None):
    # configure style
    sns.set(style='ticks', context='notebook')

    rows=len(variables)

    f, axes = plt.subplots(rows, 1, sharex=True, figsize=[8, 6])
    row=1
    for var, ax in zip(variables, axes):
        sns.boxplot(x="Variant", y=var, hue="search",
                    data=data, notch=False, width=0.5,
                    fliersize=3,
                    palette="Paired", ax=ax)
        if row > 1:
            ax.legend().set_visible(False)
        if row < rows:
            ax.set_xlabel('')

        if args.ylims and len(args.ylims) >= row and args.ylims[row-1]:
            ax.set_ylim(bottom=-5, top=args.ylims[row-1])

        row += 1

    sns.despine()
    if output:
        plt.savefig(output, bbox_inches='tight')
    else:
        plt.show()


if __name__ == '__main__':

    args = get_args()
    assert len(args.experiments) == len(args.labels)

    data = prepare_data(args.basepath, args.experiments, args.labels)
    print(data.head())

    create_plot(data, args.vars, output=args.output)
