# Copyright (C) 2018-2021 Teemu Ikonen <tpikonen@gmail.com>

# This file is part of Taival.
# Taival is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License version 3 as published by the
# Free Software Foundation. See the file COPYING for license text.

import csv
from collections import defaultdict

gtfs_stops_file = "/home/tpikonen/src/taival/digiroad_stops/hsl/stops.txt"

def read_digiroad_stops(filename):
    dialect = 'excel'
    stopdict = defaultdict(list)
    with open(filename, 'r', encoding='utf-8-sig') as fi:
        reader = csv.DictReader(fi)
        for r in reader:
            stopdict[r['stop_name']].append(r)
    return stopdict

stops_by_name = read_digiroad_stops(gtfs_stops_file)
