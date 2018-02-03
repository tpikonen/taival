#!/usr/bin/env python3
import gpxpy.gpx, overpy, argparse, requests

parser = argparse.ArgumentParser()
parser.add_argument('--version', '-v', action='version', version='0.0.1')
parser.add_argument('--line', '-l', dest='line', metavar='<lineno>', help='Public transport line to process')

api = overpy.Overpass()

def write_gpx(latlon, fname, waypoints=None):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)
    for ll in latlon:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(ll[0], ll[1]))
    if waypoints:
        for w in waypoints:
            gpx.waypoints.append(gpxpy.gpx.GPXWaypoint(w[0], w[1], name=w[2], description=w[3]))

    with open(fname, "w") as ff:
        ff.write(gpx.to_xml())




def route2gpx(rel, fname):
    """Write a gpx-file fname from an overpy relation containing
    an OSM public_transport:version=2 route."""
    nodes = rel2nodes(rel)
    platforms = [mem.resolve() for mem in rel.members if mem.role == "platform"]
    waypts = []
    for x in platforms:
        if type(x) == overpy.Way:
            lat = x.nodes[0].lat
            lon = x.nodes[0].lon
        else:
            lat = x.lat
            lon = x.lon
        name = x.tags['ref']
        desc = x.tags['name']
        waypts.append([lat,lon,name,desc])
    #latlon = [[n.lat, n.lon] for w in ways for n in w.nodes]
    latlon = [[n.lat, n.lon] for n in nodes]
    write_gpx(latlon, fname, waypoints=waypts)

def rel2nodes(rel):
    """Write a gpx-file to fname from given overpy relation object."""

    def ndist2(n1, n2):
        """Return distance metric squared for two nodes n1 and n2."""
        return (n1.lat - n2.lat)**2 + (n1.lon - n1.lon)**2

    ways = [mem.resolve() for mem in rel.members
        if isinstance(mem, overpy.RelationWay) and (mem.role is None)]
    # Initialize nodes list with first way, correctly oriented
    if (ways[0].nodes[-1] == ways[1].nodes[0]) \
      or (ways[0].nodes[-1] == ways[1].nodes[-1]):
        nodes = ways[0].nodes
    elif (ways[0].nodes[0] == ways[1].nodes[0]) \
      or (ways[0].nodes[0] == ways[1].nodes[-1]):
        nodes = ways[0].nodes[::-1] # reverse
    else:
        print("Gap between first two ways")
        begmin = min(ndist2(ways[0].nodes[0], ways[1].nodes[0]),
                     ndist2(ways[0].nodes[0], ways[1].nodes[-1]))
        endmin = min(ndist2(ways[0].nodes[-1], ways[1].nodes[0]),
                     ndist2(ways[0].nodes[-1], ways[1].nodes[-1]))
        if endmin < begmin:
            nodes = ways[0].nodes
        else:
            nodes = ways[0].nodes[::-1]
    # Combine nodes from the rest of the ways to a single list,
    # flip ways when needed
    for w in ways[1:]:
        if nodes[-1] == w.nodes[0]:
            nodes.extend(w.nodes[1:])
        elif nodes[-1] == w.nodes[-1]:
            nodes.extend(w.nodes[::-1][1:])
        else:
            print("Gap between ways")
            if ndist2(nodes[-1], w.nodes[0]) < ndist2(nodes[-1], w.nodes[-1]):
                nodes.extend(w.nodes)
            else:
                nodes.extend(w.nodes[::-1])
    return nodes


def get_rel(relno):
    rr = api.query("rel(id:%d);(._;>;>;);out body;" % (relno))
    return rr.relations[0]


def osm_rels(lineref):
    """Get public transport lines corresponding to lineno in Helsinki area."""
    area = """area[admin_level=7]["name"="Helsingin seutukunta"]["ref"="011"][boundary=administrative]->.hel;"""
    q = '%s rel(area.hel)[route="bus"][ref="%s"]["public_transport:version"="2"];(._;>;>;);out body;' % (area, lineref)
    rr = api.query(q)
    return rr


if __name__ == '__main__' and '__file__' in globals ():
    args = parser.parse_args()
    line = args.line
    print("Processing line %s" % line)
    rr = osm_rels(line)
    if len(rr.relations) > 0:
        for i in range(len(rr.relations)):
            fn = "%s_osm_%d.gpx" % (line, i)
            route2gpx(rr.relations[i], fn)
            print(fn)
    else:
        print("Line '%s' not found." % line)
