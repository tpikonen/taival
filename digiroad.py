# Copyright (C) 2018-2021 Teemu Ikonen <tpikonen@gmail.com>

# This file is part of Taival.
# Taival is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License version 3 as published by the
# Free Software Foundation. See the file COPYING for license text.

import csv
import os
import sys
from collections import defaultdict

_basedir = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])))
datadir = './data/digiroad/'

# For the data file included below:
# Source: Digiroad, Finnish Transport Infrastructure Agency. Data is downloaded
# from the Download- and Viewing Service of Finnish Transport Infrastructure
# Agency under the license CC 4.0 BY.
# URL: https://aineistot.vayla.fi/joukkoliikenne/waltti/HSL_kuntayhtyma.zip
# License: Creative Commons Attribution 4.0 International (CC BY 4.0)
# Copyright 2019 Väylävirasto / Finnish Transport Infrastructure Agency
# See https://vayla.fi/vaylista/aineistot/avoindata
gtfs_stops_file = os.path.join(_basedir,
                               os.path.join(datadir, "./stops/HSL/stops.txt"))

def read_digiroad_stops(filename):
    dialect = 'excel'
    stopdict = defaultdict(list)
    with open(filename, 'r', encoding='utf-8-sig') as fi:
        reader = csv.DictReader(fi)
        for r in reader:
            stopdict[r['stop_name']].append(r)
    return stopdict

stops_by_name = read_digiroad_stops(gtfs_stops_file)
