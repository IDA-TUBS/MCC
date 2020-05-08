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

./plot_stats.py --basepath run/ \
	--experiments "${EXPERIMENTS[@]}" \
	--labels "${NAMES[@]}" \
	--vars Iterations Operations "Total Time [s]"
