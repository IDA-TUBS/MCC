#!/usr/bin/env python

##############################################################################
# Brief:
# create subplots for iterations, operations and time
#  every subplot shows two boxplots (chrono/nonchrono) for each experiment
##############################################################################

from argparse import ArgumentParser
import seaborn as sns
import pandas as pd
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
    return parser.parse_args()


def parse_file(filename):
    data = list()
    with open(filename, 'r') as csvfile:
        reader = DictReader(csvfile, delimiter='\t')

        for row in reader:
            newrow = dict()
            newrow['Time']       = float(row['time'])
            newrow['Iterations'] = int(row['iterations'])
            newrow['Operations'] = int(row['operations'])
            newrow['run']        = int(row['run'])
            data.append(newrow)

    return data


def prepare_data(basepath, experiments, labels):

    # iterate experiments and parse files
    raw_data = list()
    for exp,label in zip(experiments, labels):
        chrono    = parse_file('%s/%s/chrono/results.csv'    % (basepath, exp))
        nonchrono = parse_file('%s/%s/nonchrono/results.csv' % (basepath, exp))

        # assert that both files have the same sample size
        assert len(chrono) == len(nonchrono)

        for r in chrono:
            r['chrono']   = 'Yes'
            r['scenario'] = label

        for r in nonchrono:
            r['chrono'] = 'No'
            r['scenario'] = label

        raw_data.extend(chrono + nonchrono)

    return pd.DataFrame(data)


def create_plot(data, variables, output=None):
    # configure style
    sns.set(style='ticks', context='talk')

    rows=len(variables)

    f, axes = plt.subplots(rows, 1, sharex=True)
    row=1
    for var, ax in zip(variables, axes):
        sns.boxplot(x="day", y=var, hue="smoker",
                    data=data, notch=False,
                    palette="muted", ax=ax)
        if row > 1:
            ax.legend().set_visible(False)
        if row < rows:
            ax.set_xlabel('')
        row += 1

    sns.despine()
    if output:
        plt.savefig(output)
    else:
        plt.show()


if __name__ == '__main__':

    args = get_args()
    assert len(args.experiments) == len(args.labels)

    data = prepare_data(args.basepath, args.experiments, args.labels)
    print(data.head())

    create_plot(data, args.vars, output=args.output)
