#!/bin/bash

##############################################################################
# Description:
#  With this script, we test the backtracking. The search is started multiple
#  times for every experiment. We log the number of iterations and operations,
#  and the time it took to find the first solution.
#  We execute the mcc with assertions disabled.
##############################################################################

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

if [ 2 = $# ]; then
	wanted_tries=$1
	wanted_succ=$2
elif [ $# -lt 1 ]; then
	echo "Usage: $0 wanted_total_tries [2]"
	exit 1
else
	wanted_tries=$1
	wanted_succ=-1
fi

printf 'wanted: tries=%d successes:%d\n' $wanted_tries $wanted_succ

run_cmd() {
	cmd_args=$1
	OUTPATH=$2

	csv="${OUTPATH}results.csv"
	echo -e "run\titerations\toperations\ttime" > "${csv}"

	cnt=0
	while true ; do
		cnt=$((cnt+1))

		cmd="python -O ./mcc_acsos.py $cmd_args 2>&1"
		out=$(unbuffer sh -c "$cmd" | tee "${OUTPATH}output-$cnt.log")

		tries=$(printf '%s\n' "$out" | grep 'Backtracking Try ' | tail -n 1 | awk '{print $4}')
		succ=$(printf '%s\n' "$out" | grep 'Backtracking succeeded in try' | wc -l)
		ops=$(printf '%s\n' "$out" | tail -n 10 | grep operations | awk '{print $NF}')
		time=$(printf '%s\n' "$out" | tail -n 10 | grep time | awk '{print $NF}' | tr -d '\n')
		if [ 2 -eq $succ ] ; then
			printf 'success'
		else
			printf 'failed'
		fi

		printf ' |'
		printf "tries: %d succeeded: %d\n" $tries $succ

		if [ 2 != $# ]; then
			break
		fi

		if [ $wanted_succ -eq $succ ] ; then
			printf ''
			echo 'found!'
			break
		fi

		numops=0
		while read -r c; do
			num=$(echo $c | tr -d '\n')
			numops=$(($numops+$num))
		done <<< "${ops[@]}"

		echo -e "$cnt\t$tries\t$numops\t$time" >> $csv

		if [ $cnt -eq $wanted_tries ] ; then
			printf ''
			echo 'end!'
			break
		fi

	done
}

run_chronological() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/test/chrono/"
	mkdir -p "${OUTPATH}"
	cmd_args="-o \"${OUTPATH}\" --chronological --basepath \"${BASEPATH}\" \"${exp}\""

	echo "Starting chronological on $exp"
	run_cmd "$cmd_args" "$OUTPATH"
}

run_nonchronological() {
	exp=$1
	OUTPATH="./run/$(basename $exp)/test/nonchrono/"
	mkdir -p "${OUTPATH}"
	cmd_args="-o \"${OUTPATH}\" --basepath \"${BASEPATH}\" \"${exp}\""

	echo "Starting non-chronological on $exp"
	run_cmd "$cmd_args" "$OUTPATH"
}

# first run, chronological BT
export -f run_cmd
export -f run_chronological
export -f run_nonchronological
export BASEPATH
export wanted_tries
export wanted_succ

if which parallel &> /dev/null; then
	parallel --gnu --ungroup -j $JOBS run_chronological ::: "${EXPERIMENTS[@]}"

	# second run, nonchronological BT
	parallel --gnu --ungroup -j $JOBS run_nonchronological ::: "${EXPERIMENTS[@]}"
else
	for exp in "${EXPERIMENTS[@]}"; do
		run_chronological $exp
		run_nonchronological $exp
	done
fi
