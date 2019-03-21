---
title: Anleitung zur Implementierung von Funktionspartitionierung/-mapping mit Hilfe von Constraint Programming
author:
- name: Johannes Schlatow
  affiliation: TU Braunschweig, IDA
  email: schlatow@ida.ing.tu-bs.de
date: \today 
abstract: Lorem ipsum.
lang: german
papersize: a4paper
numbersections: 1
draft: 1
packages:
- tubscolors
- array
- booktabs
- hyperref
- import
tikz: calc,shapes,automata,arrows,shadows,backgrounds,patterns,fit,decorations.pathreplacing
sfdefault: 1
fancyhdr: 1
compiletex: 0
scalefigures: 0
table_caption_above: 0
floatpos: ht
versiontag: draft -- \today
...
---

# Einleitung und Überblick

__Aktueller Stand__

Der _Multi-Change Controller_ sucht auf Basis einer vorgegebenen Funktionsarchitektur (_function architecture_) eine Systemkonfiguration, bestehend aus Softwarekomponenten.
Die Funktionsarchitektur wird als Graph gespeichert und visualisiert.
Dabei stellen die Knoten die Funktionsblöcke darstellen und die Kanten die (funktionalen) Abhängigkeiten 
Derzeit ist jeder Knoten bereits einer Plattformkomponente (z.B. Prozessor, Subsystem) zugewiesen (_mapping_) bevor der MCC mit seiner Suche nach einer Konfiguration beginnt.

__Ziel__

Der MCC soll um die Lösung des Mapping-Problems erweitert werden, d.h.\ gegeben eine Funktionsarchitektur sowie eine Zielplattform, soll der MCC eine Zuweisung von Funktionsblöcken auf Plattformkomponenten finden.

__Methodik__

Das Mapping-Problem ist eine bekanntes _Constraint Satisfaction Problem_ (CSP).
Es existieren diverse Methoden zur Lösung diese Problems mit unterschiedlichen Constraints und ggf.\ Optimierungszielen.
Dazu zählen _satisfiability modulo theories_ (SMT), _(integer) linear programming_ (ILP) sowie _constraint programming_ (CP).

An dieser Stelle soll CP angewandt werden.

Eine praktische Einführung ähnlicher Probleme wird auf der Website der [Google OR Tools](https://developers.google.com/optimization/introduction/overview) gegeben.

__Einschränkung__

Das Mapping-Problem beschreibt nur einen Teil der Requirements und Constraints, die im weiteren Verlauf vom MCC berücksichtigt werden müssen.
Wir gehen also davon aus, dass das Mapping-Problem nicht vollständig den Lösungsraum einschränkt, d.h.\ die formulierten Constraints sollen den Charakter von _notwendigen_ Bedingungen haben.

![Notwendige vs. hinreichende Bedingungen](figures/constraints.tikz)

# Constraints und Zielfunktion

__Gegeben:__

* Graph $G=(V,E)$ mit Knoten $V$ und Kanten $E$.
* Menge an Plattformkomponenten $P$.
* Kompatibilitätsfunktion $C(v\in V)\subseteq P$.

__Gesucht:__

* Mapping $f: V \rightarrow P$

__Constraints:__

* Verfügbarer Speicher pro $p\in P$ und Speicherkosten pro $v\in V$ (abhängig von Mapping, d.h. $f: V\times P \rightarrow \mathbb{N}$)
	* Die Summe der Speicherkosten der auf $p\in P$ gemappten $v\in V$ darf den verfügbaren Speicher nicht überschreiten.
* Utilisation pro $v\in V$ (abhängig von Mapping)
	* Die Last/Utilisation der auf $p\in P$ gemappten $v\in V$ darf 100% nicht überschreiten.
* Partitioning Constraints
	* Es können Knotenpaare $(u,v)$ definiert werden, die auf der gleichen Ressource laufen müssen.
	* Es können Knotenpaare $(u,v)$ definiert werden, die auf der unterschiedlichen Ressourcen laufen müssen.
* Size Constraints
	* Es können Mengen $g\subseteq V$ definiert werden, die nicht zusammen auf eine bestimmte Ressource passen.

__Zielfunktion:__

1. Minimierung der Partitionierungskosten
	* Für jedes Knotenpaar $(u,v)$ können Kosten (Penalty) definiert werden, wenn sie auf der gleichen Ressource laufen.
2. Minimierung der Kommunikationskosten
	* Für jede Kante $e\in E$ fallen Kommunikationskosten an, wenn sie auf unterschiedlichen Ressourcen laufen.
3. Minimierung der Kommunikationslatenz
	* Für jede Kante $e\in E$ können Kommunikationszeiten definiert werden, wenn sie auf unterschiedlichen Ressourcen laufen.

Die Reihenfolge bzw. Priorität der Zielfunktionkomponenten soll konfigurierbar sein.

# Umsetzung

## Schritt 0
_Johannes_

Die Funktionsarchitektur ist gegeben als Graph.
Eine AnalyseEngine wird implementiert, welche eine `map` Operation für den Parameter _mapping_ durchführt.
Dabei werden jedem Funktionsblock eine Menge an kompatiblen Plattformkomponenten zugewiesen ($C(v)$).

## Schritt 1
_Edgard_

Anschließend wird über eine `assign` Operation jedem Knoten eine Ressource zugewiesen.
Hierzu werden Constraints und Zielfunktionen (für die Optimierung) als CP formuliert und mittels Google OR Tools gelöst.
Wichtig ist hierbei, dass die Kosten und Constraints nicht unbedingt vollständig bekannt sind, d.h. die Implementierung muss mit fehlenden Werten umgehen können.

## Schritt 2
_Edgard_

Im weiteren Verlauf der Suche durch den MCC kann sich eine gefundenes Mapping als nicht umsetzbar herausstellen.
Hierzu ist es erforderlich die während der Suche gefundenen Partitionierungs- oder Size-Constraints als Zustand zu speichern.
Wir nehmen momentan an, dass diese Constraints für die gegeben Repositories und die gegebene Zielplattform allgemein gültig sind.

# Nützliches

* [Google OR Tools für Archlinux](https://home.schlatow.name:9443/aur-builds/or-tools-6.10-3-x86_64.pkg.tar.xz)
* [Google OR Tools Python Library für Archlinux](https://home.schlatow.name:9443/aur-builds/or-tools-6.10-3-x86_64.pkg.tar.xz)
