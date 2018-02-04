#!/usr/bin/env python3
import sys, datetime, gpxpy.gpx, overpy, argparse, requests, json
import difflib

parser = argparse.ArgumentParser()
parser.add_argument('--version', '-v', action='version', version='0.0.1')
parser.add_argument('--line', '-l', dest='line', metavar='<lineno>', help='Public transport line to process')



def write_gpx(latlon, fname, waypoints=[]):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)
    for ll in latlon:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(ll[0], ll[1]))
    for w in waypoints:
        gpx.waypoints.append(gpxpy.gpx.GPXWaypoint(w[0], w[1], name=w[2],
                                                   description=w[3]))
    with open(fname, "w") as ff:
        ff.write(gpx.to_xml())

# HSL data from GraphQL API

# Digitransit API modes: BUS, RAIL, TRAM, SUBWAY, FERRY

hslurl = "https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql"
headers = {'Content-type': 'application/graphql'}

def hsl_patterns(lineid):
    """Return a list of pattern codes corresponding to a given line ID."""
    query = '{routes(name:"%s") {\nshortName\npatterns {code}}}' % (lineid)
    #print(query)
    r = requests.post(url=hslurl, data=query, headers=headers)
    #print(r.text)
    rts = json.loads(r.text)["data"]["routes"]
    patterns = [r["patterns"] for r in rts if r["shortName"] == lineid]
    if patterns:
        codes = [d["code"] for d in patterns[0]]
    else:
        codes = []
    return codes


def hsl_patterns_for_date(lineid, datestr):
    """Get patterns which are valid (have trips) on a date given in
    YYYYMMDD format."""
    codes = hsl_patterns(lineid)
    valids = []
    for c in codes:
        query = '{pattern(id:"%s"){tripsForDate(serviceDate:"%s"){id}}}' \
          % (c, datestr)
        r = requests.post(url=hslurl, data=query, headers=headers)
        if len(json.loads(r.text)["data"]["pattern"]["tripsForDate"]) > 0:
            valids.append(c)
    return valids


def hsl_patterns_after_date(lineid, datestr):
    """Get patterns which are valid (have trips) after a date given in
    YYYYMMDD format. Can be used to discard patterns which not valid
    any more."""
    codes = hsl_patterns(lineid)
    valids = []
    dateint = int(datestr)
    for c in codes:
        query = '{pattern(id:"%s"){trips{activeDates}}}' % (c)
        r = requests.post(url=hslurl, data=query, headers=headers)
        trips = json.loads(r.text)["data"]["pattern"]["trips"]
        for t in trips:
           if any(int(d) > dateint for d in t["activeDates"]):
                valids.append(c)
                break
    return valids


def hsl_shape(code):
    """Return geometry for given pattern code as tuple (directionId, latlon)."""
    query = '{pattern(id:"%s") {directionId\ngeometry {lat\nlon}}}' % (code)
    #print(query)
    r = requests.post(url=hslurl, data=query, headers=headers)
    #print(r.text)
    pat = json.loads(r.text)["data"]["pattern"]
    dirid = pat["directionId"] # int
    latlon = [[c["lat"], c["lon"]] for c in pat["geometry"]]
    return (dirid, latlon)


def hsl_platforms(code):
    """Return stops for a given pattern code as waypoint list
    [[lat, lon, stopcode, name]]."""
    query = '{pattern(id:"%s") {stops {code\nname\nlat\nlon}}}' % (code)
    #print(query)
    r = requests.post(url=hslurl, data=query, headers=headers)
    #print(r.text)
    stops = json.loads(r.text)["data"]["pattern"]["stops"]
    return [[s["lat"], s["lon"], s["code"], s["name"]] for s in stops]


def hsl2gpx(lineref):
    """Write gpx files for given lineref from HSL digitransit API data."""
    codes = hsl_patterns(lineref)
    #print(codes)
    for c in codes:
        (dirid, latlon) = hsl_shape(c)
        stops = hsl_platforms(c)
        fname = "%s_hsl_%s_%d.gpx" % (lineref, c, dirid)
        write_gpx(latlon, fname, waypoints=stops)
        print(fname)

# OSM data from Overpass API

api = overpy.Overpass()
area = """area[admin_level=7]["name"="Helsingin seutukunta"]["ref"="011"][boundary=administrative]->.hel;"""

def osm_shape(rel):
    """Get route shape from overpy relation."""
    nodes = rel2nodes(rel)
    latlon = [[float(n.lat), float(n.lon)] for n in nodes]
    return latlon


def osm_platforms(rel):
    retval = []
    platforms = [mem.resolve() for mem in rel.members if mem.role == "platform"]
    for x in platforms:
        if type(x) == overpy.Way:
            lat = x.nodes[0].lat
            lon = x.nodes[0].lon
        else:
            lat = x.lat
            lon = x.lon
        name = x.tags['ref']
        desc = x.tags['name']
        retval.append([float(lat),float(lon),name,desc])
    return retval


def route2gpx(rel, fname):
    """Write a gpx-file fname from an overpy relation containing
    an OSM public_transport:version=2 route."""
    nodes = rel2nodes(rel)
    waypts = osm_platforms(rel)
    latlon = [[n.lat, n.lon] for n in nodes]
    write_gpx(latlon, fname, waypoints=waypts)


def ndist2(n1, n2):
    """Return distance metric squared for two nodes n1 and n2."""
    return (n1.lat - n2.lat)**2 + (n1.lon - n2.lon)**2


def rel2nodes(rel):
    """Write a gpx-file to fname from given overpy relation object."""
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


def osm_rel(relno):
    rr = api.query("rel(id:%d);(._;>;>;);out body;" % (relno))
    return rr.relations[0]


def osm_rels_v2(lineref, mode="bus"):
    """Get public transport v2 lines corresponding to lineref in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"]["public_transport:version"="2"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr


def osm_rels(lineref, mode="bus"):
    """Get all bus lines corresponding to lineref in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr


def osm2gpx(lineref):
    rr = osm_rels_v2(lineref)
    if len(rr.relations) > 0:
        for i in range(len(rr.relations)):
            fn = "%s_osm_%d.gpx" % (lineref, i)
            route2gpx(rr.relations[i], fn)
            print(fn)
    else:
        print("Line '%s' not found." % lineref)

# Comparison between OSM and HSL data


def test_route_master(lineref, route_ids):
    """Test if a route_master relation for lineref exists and contains the
    given route_ids."""
    q = '[out:json][timeout:25];(%s);(rel(br)["type"="route_master"]);out body;' \
      % (";".join(["rel(%d)" % x for x in route_ids]))
    rr = api.query(q)
    nr = len(rr.relations)
    if nr < 1:
        print("No route_master relation found.")
        return
    elif nr == 1:
        print("route_master relation exists.")
    elif nr > 1:
        print("More than one route_master relations exist!")
        return
    memrefs = [m.ref for m in rr.relations[0].members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        print("route_master has extra members, ids: %s" \
          % (str(refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        print("Found matching routes not in route_master, ids: %s" \
          % (str(routes_not_in_refs)))
    tags = rr.relations[0].tags
    if tags.get("public_transport:version", "0") != "2":
        print("Tag public_transport:version=2 not set.")
    if tags.get("network", "") != "HSL":
        print("Tag network is not 'HSL'.")


def ldist2(p1, p2):
    """Return distance metric squared for two latlon pairs."""
    d = (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2
    return d


def get_correspondance(ids1, ids2, shapes1, shapes2):
    """Determine corresponding shape ids from their geometries.
    Return permutation indices for both directions."""
    m1to2 = [-1]*len(ids1)
    m2to1 = [-1]*len(ids2)
    for i in range(len(ids1)):
        mind = 1.0e10
        minind = 0
        cbeg = shapes1[i][0]
        cend = shapes1[i][-1]
        for j in range(len(ids2)):
            d = min(ldist2(cbeg, shapes2[j][0]), ldist2(cend, shapes2[j][-1]))
            if d < mind:
                mind = d
                minind = j
        m1to2[i] = minind
    for i in range(len(m1to2)):
        m2to1[m1to2[i]] = i
    if any(v < 0 for v in m1to2 + m2to1):
        print("No good route correspondance found.")
    return (m1to2, m2to1)


def compare(lineref):
    """Report on differences between OSM and HSL data for a given line."""
    rr = osm_rels(lineref)
    if(len(rr.relations) < 1):
        print("No route relations found in OSM.")
        return
    relids = [r.id for r in rr.relations]
    print("Found OSM route ids: %s" % (relids))
    if len(rr.relations) > 2:
        print("More than 2 OSM routes found, giving up.")
        return
    codes = hsl_patterns_after_date(lineref, \
                                    datetime.date.today().strftime("%Y%m%d"))
    print("Found HSL pattern codes: %s" % (codes))
    if len(codes) > 2:
        print("More than 2 HSL patterns found, giving up.")
        return
    #test_route_master(lineref, [r.id for r in rr.relations])
    for rel in rr.relations:
        #print("OSM route %s" % (rel.id))
        if rel.tags.get("public_transport:version", "0") != "2":
            print("Tag public_transport:version=2 not set in OSM route %s. Giving up." % (rel.id))
    osmshapes = [osm_shape(rel) for rel in rr.relations]
    hslshapes = [hsl_shape(c)[1] for c in codes]
    (osm2hsl, hsl2osm) = get_correspondance(relids, codes, osmshapes, hslshapes)
    for i in range(len(relids)):
        print("%s -> %s" % (relids[i], codes[osm2hsl[i]]))
    for i in range(len(codes)):
        print("%s -> %s" % (codes[i], relids[hsl2osm[i]]))
    osmplatforms = [osm_platforms(rel) for rel in rr.relations]
    hslplatforms = [hsl_platforms(c) for c in codes]
    for i in range(len(osmplatforms)):
        print("Comparing platforms for OSM id %d vs pattern %s" \
            % (relids[i], codes[osm2hsl[i]]))
        osmp = [p[2]+"\n" for p in osmplatforms[i]]
        hslp = [p[2]+"\n" for p in hslplatforms[osm2hsl[i]]]
        sys.stdout.writelines(difflib.unified_diff(osmp, hslp))


if __name__ == '__main__' and '__file__' in globals ():
    args = parser.parse_args()
    line = args.line
    if line is None:
        sys.exit(1)
    print("Processing line %s" % line)
    osm2gpx(line)
    hsl2gpx(line)
