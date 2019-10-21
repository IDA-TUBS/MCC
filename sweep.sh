#!/bin/sh

##############################################################################
# Description:
#  With this script, we sweep the solution space of all experiments.
#  We do this by running the chronological backtracking.
#
#  The BacktrackingTestEngine writes a csv file with the statistics.
#  The output.log will also contain information about the number of
#  failed operations per AnalysisEngine.
#
#  For testing purposes, we do the same with non-chronological backtracking
#  to see whether we get the same result.
##############################################################################

#setuplm pycpa testing

BASEPATH="./models/rtas/"

EXPERIMENTS=(
"./models/rtas/queries/pose_no_fpga_low_rel.xml"
"./models/rtas/queries/pose_fpga_low_rel.xml"
"./models/rtas/queries/pose_fpga_high_rel.xml"
"./models/rtas/queries/obj_no_fpga_low_rel.xml"
"./models/rtas/queries/obj_fpga_low_rel.xml"
"./models/rtas/queries/obj_fpga_high_rel.xml"
)

JOBS=2

if [ $# -ge 1 ]; then
	if [ "$1" == "clean" ]; then
		for exp in "${EXPERIMENTS[@]}"; do
			OUTPATH="./run/$(basename $exp)/sweep/"
			rm -r "${OUTPATH}"
		done
		exit 0
	fi
fi

run_chronological() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/sweep/chrono/"
	mkdir -p "${OUTPATH}"

	cmd="./mcc_rtas.py --explore --chronological --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	[ -z $? ] && echo "   SUCCEEDED" || echo "   FAILED"
}

run_nonchronological() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/sweep/nonchrono/"
	mkdir -p "${OUTPATH}"

	cmd="./mcc_rtas.py --explore --basepath \"${BASEPATH}\" --outpath \"${OUTPATH}\" \"$exp\" 2>&1"
	echo "Running $cmd"
	unbuffer sh -c "$cmd" > "${OUTPATH}output.log"
	[ -z $? ] && echo "   SUCCEEDED" || echo "   FAILED"
}

# first run, chronological BT
export -f run_chronological
export -f run_nonchronological
export BASEPATH

parallel --gnu --ungroup -j $JOBS run_chronological ::: "${EXPERIMENTS[@]}"

# second run, nonchronological BT
parallel --gnu --ungroup -j $JOBS run_nonchronological ::: "${EXPERIMENTS[@]}"

