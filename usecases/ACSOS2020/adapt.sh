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

BASEPATH="../../models/acsos/"

EXPERIMENTS=(
"../../models/acsos/queries/pose_no_fpga_low_rel.xml"
"../../models/acsos/queries/pose_fpga_low_rel.xml"
"../../models/acsos/queries/pose_fpga_high_rel.xml"
"../../models/acsos/queries/obj_no_fpga_low_rel.xml"
"../../models/acsos/queries/obj_fpga_low_rel.xml"
"../../models/acsos/queries/obj_fpga_high_rel.xml"
)

JOBS=2

if [ $# -ge 1 ]; then
	if [ "$1" == "clean" ]; then
		for exp in "${EXPERIMENTS[@]}"; do
			OUTPATH="./run/$(basename $exp)/adapt/"
			rm -r "${OUTPATH}"
		done
		exit 0
	fi
fi

run_adapt110() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/adapt110/nonchrono/"
	mkdir -p "${OUTPATH}"

	cmd="./mcc_acsos.py --adapt --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	succ=$(cat "${OUTPATH}output.log" | grep 'Stats' | wc -l)
	if [ 2 -eq $succ ] ; then
		echo '  SUCCEEDED'
	else
		echo '  FAILED'
	fi
}

run_adapt200() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/adapt200/nonchrono/"
	mkdir -p "${OUTPATH}"

	cmd="./mcc_acsos.py --adapt --wcet_factor 2.0 --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	succ=$(cat "${OUTPATH}output.log" | grep 'Stats' | wc -l)
	if [ 2 -eq $succ ] ; then
		echo '  SUCCEEDED'
	else
		echo '  FAILED'
	fi
}

run_adapt150() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/adapt150/nonchrono/"
	mkdir -p "${OUTPATH}"

	cmd="./mcc_acsos.py --adapt --wcet_factor 1.5 --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	succ=$(cat "${OUTPATH}output.log" | grep 'Stats' | wc -l)
	if [ 2 -eq $succ ] ; then
		echo '  SUCCEEDED'
	else
		echo '  FAILED'
	fi
}

export -f run_adapt110
export -f run_adapt150
export -f run_adapt200
export BASEPATH

if which parallel &> /dev/null; then
	parallel --gnu --ungroup -j $JOBS run_adapt200 ::: "${EXPERIMENTS[@]}"

	parallel --gnu --ungroup -j $JOBS run_adapt150 ::: "${EXPERIMENTS[@]}"

	parallel --gnu --ungroup -j $JOBS run_adapt110 ::: "${EXPERIMENTS[@]}"
else
	for exp in "${EXPERIMENTS[@]}"; do
		run_adapt200 $exp
		run_adapt150 $exp
		run_adapt110 $exp
	done
fi


