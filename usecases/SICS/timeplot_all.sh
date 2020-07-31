#!/bin/sh

EXPERIMENTS=(
"obj_no_fpga_low_rel.xml"
"obj_fpga_low_rel.xml"
"obj_fpga_high_rel.xml"
)

NAMES=(
"OBJ I"
"OBJ II"
"OBJ III"
)

SERIES=(
"adapt110"
"adapt150"
"adapt200"
)

./plot_timeline.py --basepath run/ \
	--experiments "${EXPERIMENTS[@]}" \
	--labels "${NAMES[@]}" \
	--series "${SERIES[@]}" \
	--vars Iterations "Time [s]" Complexity

EXPERIMENTS=(
"pose_no_fpga_low_rel.xml"
"pose_fpga_low_rel.xml"
"pose_fpga_high_rel.xml"
)

NAMES=(
"POSE I"
"POSE II"
"POSE III"
)

./plot_timeline.py --basepath run/ \
	--experiments "${EXPERIMENTS[@]}" \
	--labels "${NAMES[@]}" \
	--series "${SERIES[@]}" \
	--vars Iterations "Time [s]" Complexity
