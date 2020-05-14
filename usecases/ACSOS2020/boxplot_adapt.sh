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
"adapt110-nonchrono"
"adapt110-replay"
"adapt150-nonchrono"
"adapt150-replay"
"adapt200-nonchrono"
"adapt200-replay"
)

./plot_stats_adapt.py --basepath run/ \
	--experiments "${EXPERIMENTS[@]}" \
	--labels "${NAMES[@]}" \
	--series "${SERIES[@]}" \
	--vars Iterations Operations "Time [s]"
