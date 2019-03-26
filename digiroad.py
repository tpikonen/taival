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
