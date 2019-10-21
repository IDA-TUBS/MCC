#!/bin/sh

EXPERIMENTS=(
"pose_no_fpga_low_rel.xml"
"pose_fpga_low_rel.xml"
"pose_fpga_high_rel.xml"
"obj_no_fpga_low_rel.xml"
"obj_fpga_low_rel.xml"
"obj_fpga_high_rel.xml"
)

if [ $# -lt 1 ]; then
    echo "Usage: $0 <basedir>"
    exit 1
fi

BASEDIR=$1

# Output Table Header
echo "Name\&Solutions\&Variables\&Combinations\&Operations\\\\"
for exp in "${EXPERIMENTS[@]}"; do
    OUTPATH="${BASEDIR}/$(basename $exp)/sweep"

    ./generate_table_row.py --name $(basename $exp) "${OUTPATH}/chrono/solutions.csv" "${OUTPATH}/nonchrono/solutions.csv"
done
