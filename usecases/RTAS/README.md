# Reproducing Results

In order to only re-run the evaluation, please extract [run.tar.xz] and continue run the evaluation
scripts.

[run.tar.xz]: run.tar.xz

## Running the experiments

We provide the following wrapper scripts for running the MCC for this use case with the appropriate parameters.

* [sweep.sh]: Finds all solutions to perform a sweep over the entire solution space.
* [test.sh]: Calls the MCC 100 times for every scenario and collects statistics.
* [adapt.sh]: Calls the MCC and challenges it with adaptations of worst-case execution times.

[sweep.sh]: sweep.sh
[test.sh]: test.sh
[adapt.sh]: adapt.sh

## Running the evaluation

We provide the following evaluation scripts:

* [generate_table.sh]: Generates a LaTeX table from the sweep results.
* [boxplot.sh]: Generates boxplots from the test results.
* [boxplot_adapt.sh]: Generates boxplots from the adaptation results.
* [timeline_all.sh]: Generates a line chart from the adaptation results for all scenarios.
* [timeline.sh]: Generates a line chart from the adaptation results for a single scenario.

