#!/usr/bin/env python

# arguments: input files (chrono and nonchrono)

from argparse import ArgumentParser
import csv
import sys

def get_args():
    descr = 'TODO'
    parser = ArgumentParser(description=descr)
    parser.add_argument('files',  nargs=2,
        help="first file shall contain the chronological BT results, second file non-chronological BT results")
    parser.add_argument('--name', required=True)
    return parser.parse_args()

def parse_results(filename):
    solutions = list()

    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')

        for row in reader:
            for k in row:
                row[k] = int(row[k])
            solutions.append(row)

    return solutions

def process_results(results):
    min_vars = None
    max_vars = None
    min_ops  = None
    max_ops  = None
    min_combs = None
    max_combs = None
    sum_iter  = 0
    sum_rolledback = 0
    for s in results:
        if not min_vars:
            min_vars = s['total_variables']
        elif min_vars > s['total_variables']:
            min_vars = s['total_variables']

        if not max_vars:
            max_vars = s['total_variables']
        elif max_vars < s['total_variables']:
            max_vars = s['total_variables']

        if not min_ops:
            min_ops = s['operations']
        elif min_ops > s['operations']:
            min_ops = s['operations']

        if not max_ops:
            max_ops = s['operations']
        elif max_ops < s['operations']:
            max_ops = s['operations']

        if not min_combs:
            min_combs = s['combinations']
        elif min_combs > s['combinations']:
            min_combs = s['combinations']

        if not max_combs:
            max_combs = s['combinations']
        elif max_combs < s['combinations']:
            max_combs = s['combinations']

        sum_iter += s['iterations']
        sum_rolledback += s['rolledback']

    return     { 'min_vars'  : min_vars,
                 'max_vars'  : max_vars,
                 'min_ops'   : min_ops,
                 'max_ops'   : max_ops,
                 'min_combs' : min_combs,
                 'max_combs' : max_combs,
                 'solutions' : len(results),
                 'iterations': sum_iter,
                 'total_ops' : sum_rolledback + results[-1]['operations']
               }

def compare_results(res1, res2):
    # assert that some values are the same in both files:
    assert res1['solutions'] == res2['solutions'], \
            'Number of solutions differ: %d vs %d' % (res1['solutions'], res2['solutions'])
    assert res1['min_vars'] == res2['min_vars'], 'Minimum number of variables differ.'
    assert res1['max_vars'] == res2['max_vars'], 'Maximum number of variables differ.'
    assert res1['min_ops'] == res2['min_ops'], 'Minimum number of operations differ.'
    assert res1['max_ops'] == res2['max_ops'], 'Maximum number of operations differ.'
    assert res1['min_combs'] == res2['min_combs'], 'Minimum number of combinations differ.'
    assert res1['max_combs'] == res2['max_combs'], 'Maximum number of combinations differ.'

    # compare other values between both files
    #  and print differences to stderr
    if res1['iterations'] != res2['iterations']:
        print("Iterations differ: %d vs %d" % (res1['iterations'], res2['iterations']), file=sys.stderr)

    if res1['total_ops'] != res2['total_ops']:
        print("Total operations differ: %d vs %d" % (res1['total_ops'], res2['total_ops']), file=sys.stderr)

def format_range(res, name):
    minval = res['min_%s' % name]
    maxval = res['max_%s' % name]

    if minval != maxval:
        return "%d-%d" % (minval, maxval)
    else:
        return "%d" % minval

if __name__ == '__main__':

    args = get_args()

    res1 = process_results(parse_results(args.files[0]))
    res2 = process_results(parse_results(args.files[1]))
    compare_results(res1, res2)

    # output a latex table row
    print("%s&%d&%s&%s&%s\\\\" % (args.name,
                               res1['solutions'],
                               format_range(res1, 'vars'),
                               format_range(res1, 'combs'),
                               format_range(res1, 'ops')))
