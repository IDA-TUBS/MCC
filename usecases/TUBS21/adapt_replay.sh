#!/bin/bash

##############################################################################
# Description:
#  With this script, we simulate an adaptation scenario
#
#  The AdaptationSimulation writes a csv file with the statistics.
#  The output.log will also contain information about the number of
#  failed operations per AnalysisEngine.
##############################################################################

#setuplm pycpa testing

BASEPATH="../../models/tubs/"

EXPERIMENTS=(
"../../models/tubs/queries/pose_no_fpga_low_rel.xml"
"../../models/tubs/queries/pose_fpga_low_rel.xml"
"../../models/tubs/queries/pose_fpga_high_rel.xml"
"../../models/tubs/queries/obj_no_fpga_low_rel.xml"
"../../models/tubs/queries/obj_fpga_low_rel.xml"
"../../models/tubs/queries/obj_fpga_high_rel.xml"
)

JOBS=2

REPEAT=50

OUTFOLDER="replay-adapt"
ARGS=""
if [ $# -ge 1 ]; then
	if [ "$1" == "clean" ]; then
		for exp in "${EXPERIMENTS[@]}"; do
			rm -r "./run/$(basename $exp)/adapt110/replay-adapt"
			rm -r "./run/$(basename $exp)/adapt150/replay-adapt"
			rm -r "./run/$(basename $exp)/adapt200/replay-adapt"
			rm -r "./run/$(basename $exp)/adapt110/replay-fromscratch"
			rm -r "./run/$(basename $exp)/adapt150/replay-fromscratch"
			rm -r "./run/$(basename $exp)/adapt200/replay-fromscratch"
		done
		exit 0
	fi
	if [ "$1" == "from_scratch" ]; then
		OUTFOLDER="replay-fromscratch"
		ARGS="--from_scratch"
	fi
fi

run_adapt110() {
	exp=$1
	num=$2
	INPATH="./run/$(basename $exp)/adapt110/nonchrono/adaptations.csv"
	OUTPATH="./run/$(basename $exp)/adapt110/$OUTFOLDER/"
	mkdir -p "${OUTPATH}"

	cmd="python -O ./mcc_tubs.py --replay_adapt \"${INPATH}\" $ARGS --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	exp=$(cat "${INPATH}" | wc -l)
	succ=$(cat "${OUTPATH}solutions.csv" | wc -l)
	rm ${OUTPATH}*.dot ${OUTPATH}*.pickle
	mv ${OUTPATH}solutions.csv ${OUTPATH}solutions-${num}.csv
	if [ $exp -eq $succ ] ; then
		echo '  SUCCEEDED'
	else
		echo '  FAILED'
	fi
}

run_adapt200() {
	exp=$1
	num=$2
	INPATH="./run/$(basename $exp)/adapt200/nonchrono/adaptations.csv"
	OUTPATH="./run/$(basename $exp)/adapt200/$OUTFOLDER/"
	mkdir -p "${OUTPATH}"

	cmd="python -O ./mcc_tubs.py --replay_adapt \"${INPATH}\" $ARGS --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	exp=$(cat "${INPATH}" | wc -l)
	succ=$(cat "${OUTPATH}solutions.csv" | wc -l)
	rm ${OUTPATH}*.dot ${OUTPATH}*.pickle
	mv ${OUTPATH}solutions.csv ${OUTPATH}solutions-${num}.csv
	if [ $exp -eq $succ ] ; then
		echo '  SUCCEEDED'
	else
		echo '  FAILED'
	fi
}

run_adapt150() {
	exp=$1
	num=$2
	INPATH="./run/$(basename $exp)/adapt150/nonchrono/adaptations.csv"
	OUTPATH="./run/$(basename $exp)/adapt150/$OUTFOLDER/"
	mkdir -p "${OUTPATH}"

	cmd="python -O ./mcc_tubs.py --replay_adapt \"${INPATH}\" $ARGS --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	exp=$(cat "${INPATH}" | wc -l)
	succ=$(cat "${OUTPATH}solutions.csv" | wc -l)
	rm ${OUTPATH}*.dot ${OUTPATH}*.pickle
	mv ${OUTPATH}solutions.csv ${OUTPATH}solutions-${num}.csv
	if [ $exp -eq $succ ] ; then
		echo '  SUCCEEDED'
	else
		echo '  FAILED'
	fi
}

export -f run_adapt110
export -f run_adapt150
export -f run_adapt200
export BASEPATH
export OUTFOLDER
export ARGS

NUM=0
while true ; do
	NUM=$((NUM+1))
	if which parallel &> /dev/null; then
		parallel --gnu --ungroup -j $JOBS run_adapt200 {} $NUM ::: "${EXPERIMENTS[@]}"

		parallel --gnu --ungroup -j $JOBS run_adapt150 {} $NUM ::: "${EXPERIMENTS[@]}"

		parallel --gnu --ungroup -j $JOBS run_adapt110 {} $NUM ::: "${EXPERIMENTS[@]}"
	else
		for exp in "${EXPERIMENTS[@]}"; do
			run_adapt200 $exp $NUM
			run_adapt150 $exp $NUM
			run_adapt110 $exp $NUM
		done
	fi

	if [ $NUM -eq $REPEAT ] ; then
		printf ''
		echo 'end!'
		break
	fi
done


