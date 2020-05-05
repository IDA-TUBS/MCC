# Description

This repository implements the Multi-Change Controller (MCC), which is a framework for model-based
self-integration of embedded software systems.
The work on this implementation was done in the scope of the DFG Research Unit _Controlling Concurrent Change_ (FOR1800).
More details can be found on the [project's website](https://ccc-project.org).

Please be aware that this software is [licensed under BSD-3-clause](LICENSE).

# Dependencies/Installation

There are a few non-standard python modules that are required for running the MCC:

* ortools
* pycpa
* networkx
* xdot

In order to execute scripts at another place than the top-level directory, you must set the PYTHONPATH variable:

```
export PYTHONPATH=/path/to/MCC:$PYTHONPATH
```

Alternatively you can install the MCC as follows (note, that this will link to the repository so that changes will take effect immediately):

```
pip install -e . --user
```


# Repository structure

Following we briefly summarise what the scripts and directories are supposed to do and contain. Please note, that you may find additional README files in the subdirectories.


## Scripts

mcc.py
: This is a general script for executing the MCC. It is not very convenient though as it must be provided with quite a few arguments. The use-case specific implementations have more convenient scripts.

view.py
: This is the model viewer with which you can browse exported pickle files interactively.

check_xml.py
: Checks validity of XML files according to the XSD.

check_all_xml.sh
: Checks all XML files in models/ for validity.


## Directories

doc
: Config files for generating Sphinx documentation.

mcc
: Contains the python sub-modules of the mcc module.

models
: Contains XML files (repositories, platforms, queries).

usecases
: Use-case specific implementations.

viewer
: Contains the python sub-modules used by `view.py`.

xsd
: XML Schema Definition files.


# Publications

* \[IECON17\]: Johannes Schlatow, Marcus Nolte, Mischa Möstl, Inga Jatzkowski, Rolf Ernst und Markus Maurer, **Towards model-based integration of component-based automotive software systems** in *Annual Conference of the IEEE Industrial Electronics Society (IECON17)*, (Beijing, China), Oktober 2017.
