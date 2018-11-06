#!/bin/bash

mkdir /tmp/checkxml
python ./check_xml.py  --batch models/ --dotpath /tmp/checkxml/
