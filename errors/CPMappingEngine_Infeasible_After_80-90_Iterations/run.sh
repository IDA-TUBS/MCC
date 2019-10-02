#!/bin/bash
rm -r outdir
mkdir outdir
../../mcc_c1.py -o outdir/ --basepath models/ mcc_control.xml
