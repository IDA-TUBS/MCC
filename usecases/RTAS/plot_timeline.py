#!/usr/bin/env python

##############################################################################
# Brief:
# create subplots with adaptation timeline
#  every experiment gets its own subplot
#  every variable gets its own y-axis and line
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
                        help='each variable gets its own line')
    parser.add_argument('--experiments', nargs='+',
                        help='directory names of all included experiments (each experiment gets its own subplot)')
    parser.add_argument('--labels', nargs='+',
                        help='labels for the experiments')
    parser.add_argument('--xvar', default="Adaptation",
                        help='x-axis')
    parser.add_argument('--output', default=None, required=False,
                        help='save plot to given file')
    return parser.parse_args()


def parse_file(filename):
    data = list()
    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')

        last_ops = 0
        for row in reader:
            newrow = dict()
#            newrow['Time [s]']   = float(row['time'])
            newrow['Iterations'] = int(row['iterations'])
            newrow['Combinations']= int(row['combinations'])
            newrow['Operations'] = int(row['rolledback']) + int(row['operations']) - last_ops
            newrow['Adaptation'] = int(row['solution'])
#            newrow['Complexity'] = int(row['complexity'])
            data.append(newrow)
            last_ops             = int(row['operations'])

    return data


def prepare_data(basepath, experiments, labels):
    result = dict()

    # iterate experiments and parse files
    for exp,label in zip(experiments, labels):
        raw_data = parse_file('%s/%s/adapt/nonchrono/solutions.csv' % (basepath, exp))

        result[label] = pd.DataFrame(raw_data)

    return result


def create_plot(data, labels, output=None):
    # configure style
    sns.set(style='ticks', context='notebook')

    rows=len(labels)

    f, axes = plt.subplots(rows, 1, sharex=False, figsize=[6, 9])
    row=1
    for exp, ax in zip(labels, axes):
        varnum = 0
        curax = ax
        for var in args.vars:
            if varnum > 0:
                curax = ax.twinx()

            if varnum > 1:
                curax.spines["right"].set_position(("outward", 80))

            color = sns.color_palette("muted")[varnum]
            sns.lineplot(x=args.xvar, y=var,
                        data=data[exp], color=color,
                        label=var, legend=False,
                        ax=curax)

            curax.yaxis.label.set_color(color)
            curax.tick_params(axis='y', colors=color)

            varnum += 1

        if row == 1:
            ax.figure.legend()

        ax.set_xlabel(exp)
        row += 1

    #sns.despine()
    if output:
        plt.savefig(output, bbox_inches='tight')
    else:
        plt.tight_layout()
        plt.show()


if __name__ == '__main__':

    args = get_args()
    assert len(args.experiments) == len(args.labels)

    data = prepare_data(args.basepath, args.experiments, args.labels)

    create_plot(data, args.labels, output=args.output)
