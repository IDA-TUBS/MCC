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
                        help='directory names of subseries (corresponds to bars in a box group)')
    parser.add_argument('--outliers', default=None, type=int,
                        help='maximum number of iterations to include')
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
            newrow['Adaptation'] = int(row['solution'])
            newrow['Complexity'] = int(row['complexity'])
            last_time            = float(row['time'])
            last_ops             = int(row['operations'])

            if args.outliers and int(row['iterations']) > args.outliers:
                print("Ignoring outlier with %d iterations" % int(row['iterations']))
                continue

            data.append(newrow)

    return data


def prepare_data(basepath, experiments, labels, series):
    raw_data = list()

    # iterate experiments and parse files
    for exp,label in zip(experiments, labels):
        for serie in series:
            result = parse_file('%s/%s/%s/nonchrono/solutions.csv' % (basepath, exp, serie))

            max_adapt = result[-1]['Adaptation']
            print("Experiment %s (%s) had %s adaptations" % (label, serie, max_adapt))

            for r in result:
                r['Increase'] = "%d%%" % (int(serie[-3:]) - 100)
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
        sns.boxplot(x="Variant", y=var, hue="Increase",
                    data=data, notch=False,
                    fliersize=3, width=0.6,
                    palette="muted", ax=ax)
        if row > 1:
            ax.legend().set_visible(False)
        if row < rows:
            ax.set_xlabel('')

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
