#!/bin/sh

EXPERIMENTS=(
"obj_no_fpga_low_rel.xml"
"obj_fpga_low_rel.xml"
"obj_fpga_high_rel.xml"
"pose_no_fpga_low_rel.xml"
"pose_fpga_low_rel.xml"
"pose_fpga_high_rel.xml"
)

NAMES=(
"OBJ I"
"OBJ II"
"OBJ III"
"POSE I"
"POSE II"
"POSE III"
)

SERIES=(
"adapt110"
"adapt150"
"adapt200"
)

./plot_stats_adapt.py --basepath run/ \
	--experiments "${EXPERIMENTS[@]}" \
	--labels "${NAMES[@]}" \
	--series "${SERIES[@]}" \
	--vars Iterations Operations "Time [s]"
