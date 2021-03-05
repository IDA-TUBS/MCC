#!/bin/sh

EXPERIMENTS=(
"pose_fpga_low_rel.xml"
)

NAMES=(
"POSE II"
)

SERIES=(
"adapt110"
#"adapt200"
)

./plot_timeline.py --basepath run/ \
	--experiments "${EXPERIMENTS[@]}" \
	--labels "${NAMES[@]}" \
	--series "${SERIES[@]}" \
	--vars Iterations "Time [s]" Complexity
