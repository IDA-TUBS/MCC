#!/usr/bin/env python3

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
    parser.add_argument('--series', nargs='+',
                        help='directory names of subseries')
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
        time_offset = 0
        last_its = 0
        for row in reader:
            newrow = dict()
            if time_offset == 0:
                newrow['Time [s]']   = 0
                time_offset = float(row['time'])
            else:
                newrow['Time [s]']   = float(row['time']) - time_offset
            newrow['Iterations'] = int(row['iterations']) + last_its
            newrow['Combinations']= int(row['combinations'])
            newrow['Operations'] = int(row['rolledback']) + int(row['operations']) - last_ops
            newrow['Adaptation'] = int(row['solution'])
            newrow['Complexity'] = int(row['complexity'])
            data.append(newrow)
            last_ops             = int(row['operations'])
            last_its             = int(row['iterations']) + last_its

    return data


def prepare_data(basepath, experiments, labels, series):
    result = dict()

    for label in labels:
        result[label] = dict()

    # iterate experiments and parse files
    for exp,label in zip(experiments, labels):
        for serie in series:
            raw_data = parse_file('%s/%s/%s/nonchrono/solutions.csv' % (basepath, exp, serie))

            result[label][serie] = pd.DataFrame(raw_data)

    return result


def create_plot(data, labels, series, output=None):
    # configure style
    sns.set(style='ticks', context='notebook')

    experiments = [(label, serie) for label in labels for serie in series]
    rows=len(experiments)

    f, axes = plt.subplots(rows, 1, sharex=False, figsize=[6, 2])
    if rows == 1:
        axes = [axes]
    row=1
    for (exp, serie), ax in zip(experiments, axes):
        varnum = 0
        curax = ax
        for var in args.vars:
            if varnum > 0:
                curax = ax.twinx()

            if varnum > 1:
                curax.spines["right"].set_position(("outward", 65))

            color = sns.color_palette("colorblind")[varnum]
            sns.lineplot(x=args.xvar, y=var,
                        data=data[exp][serie], color=color,
                        label=var, legend=False,
                        ax=curax)

            curax.yaxis.label.set_color(color)
            curax.tick_params(axis='y', colors=color)

            varnum += 1

#        if row == 1:
#            ax.figure.legend(loc='lower right')

        ax.set_xlabel("%s (%d%%)" % (exp, int(serie[-3:])-100))
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

    data = prepare_data(args.basepath, args.experiments, args.labels, args.series)

    create_plot(data, args.labels, args.series, output=args.output)
