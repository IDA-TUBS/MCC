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

if [ $# -lt 1 ]; then
    echo "Usage: $0 <basedir>"
    exit 1
fi

BASEDIR=$1

# Output Table Header
cnt=0
echo "\\toprule"
echo "Variant&Solutions&Variables&Combinations&Operations\\\\"
echo "\\midrule"
for exp in "${EXPERIMENTS[@]}"; do
    OUTPATH="${BASEDIR}/$(basename $exp)/sweep"

    ./generate_table_row.py --name "${NAMES[$cnt]}" "${OUTPATH}/chrono/solutions.csv" "${OUTPATH}/nonchrono/solutions.csv"
    cnt=$(($cnt+1))
done
echo "\\bottomrule"

echo -e "\\n"

cnt=0
for exp in "${EXPERIMENTS[@]}"; do
    OUTPATH="${BASEDIR}/$(basename $exp)/sweep"

    sol1=$(cat ${OUTPATH}/chrono/output.log | grep Solutions | awk '{print $NF}')
    sol2=$(cat ${OUTPATH}/nonchrono/output.log | grep Solutions | awk '{print $NF}')
    chrono=$(cat ${OUTPATH}/chrono/output.log | grep failed_ops | grep "##")
    nonchrono=$(cat ${OUTPATH}/nonchrono/output.log | grep failed_ops | grep "##")


    lat1=$(echo "$chrono"    | grep CPAEngine   | awk '{print $NF}')
    lat2=$(echo "$nonchrono" | grep CPAEngine   | awk '{print $NF}')
    rel1=$(echo "$chrono"    | grep Reliability | awk '{print $NF}')
    rel2=$(echo "$nonchrono" | grep Reliability | awk '{print $NF}')
    oth1=$(echo "$chrono"    | grep Protocol    | awk '{print $NF}')
    oth2=$(echo "$nonchrono" | grep Protocol    | awk '{print $NF}')

    echo -e "${NAMES[$cnt]} failed on latency:     \\t$(($lat1-$sol1)) \\t$((lat2-$sol2))"
    echo -e "${NAMES[$cnt]} failed on reliability: \\t$rel1 \\t$rel2"
    echo -e "${NAMES[$cnt]} failed on other:       \\t$oth1 \\t$oth2"

    cnt=$(($cnt+1))
done
