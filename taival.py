#!/usr/bin/env python3
import sys, datetime, gpxpy.gpx, overpy, argparse, requests, json, difflib, re
from collections import defaultdict
from math import radians, degrees, cos, sin, asin, sqrt
from hsl import *

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


# Haversine function nicked from: https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
def haversine(p1, p2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    (lat1, lon1) = (p1[0], p1[1])
    (lat2, lon2) = (p2[0], p2[1])
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return c * r


def inv_haversine(d):
    """Return latitude difference in degrees of a north-south distance d.
    Can be used as an approximate inverse of haversine function."""
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return degrees(d/r)


# OSM data from Overpass API

api = overpy.Overpass()
area = """area[admin_level=7]["name"="Helsingin seutukunta"]["ref"="011"][boundary=administrative]->.hel;"""


def osm_relid2url(relid):
    return "https://www.openstreetmap.org/relation/" + str(relid)


def osm_all_linerefs(mode="bus"):
    """Return a lineref:[urllist] dict of all linerefs in Helsinki region.
    URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(osm_relid2url(r.id))
    #refs = {r.tags["ref"]:osm_relid2url(r.id)
    #        for r in rr.relations if "ref" in r.tags.keys()}
    return refs


def osm_ptv2_linerefs(mode="bus"):
    """Return a lineref:url dict of linerefs with public_transport:version=2
    tag in Helsinki region.
    URL points to the relation in OSM."""
    q = '%s rel(area.hel)[route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"]["public_transport:version"="2"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = {r.tags["ref"]:osm_relid2url(r.id)
            for r in rr.relations if "ref" in r.tags.keys()}
    return refs


def osm_shape(rel):
    """Get route shape from overpy relation. Return a ([[lat,lon]], gaps)
    tuple, where gaps is True if the ways in route do not share endpoint
    nodes. """
    ways = [mem.resolve() for mem in rel.members
        if isinstance(mem, overpy.RelationWay) and (mem.role is None)]
    gaps = False
    if not ways:
        return ([], gaps)
    elif len(ways) == 1:
        latlon = [[float(n.lat), float(n.lon)] for n in ways[0].nodes]
        return (latlon, gaps)
    # Initialize nodes list with first way, correctly oriented
    if (ways[0].nodes[-1] == ways[1].nodes[0]) \
      or (ways[0].nodes[-1] == ways[1].nodes[-1]):
        nodes = ways[0].nodes
    elif (ways[0].nodes[0] == ways[1].nodes[0]) \
      or (ways[0].nodes[0] == ways[1].nodes[-1]):
        nodes = ways[0].nodes[::-1] # reverse
    else:
        #print("Gap between first two ways")
        gaps = True
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
            #print("Gap between ways")
            gaps = True
            if ndist2(nodes[-1], w.nodes[0]) < ndist2(nodes[-1], w.nodes[-1]):
                nodes.extend(w.nodes)
            else:
                nodes.extend(w.nodes[::-1])
    latlon = [[float(n.lat), float(n.lon)] for n in nodes]
    return (latlon, gaps)

def osm_member_coord(x):
    """Return (lat, lon) coordinates from a resolved relation member.
    Could be improved by calculating center of mass from ways etc."""
    if type(x) == overpy.Way:
        x.get_nodes(resolve_missing=True)
        lat = x.nodes[0].lat
        lon = x.nodes[0].lon
    elif type(x) == overpy.Relation:
        m = x.members[0].resolve(resolve_missing=True)
        (lat, lon) = osm_member_coord(m)
    else:
        lat = x.lat
        lon = x.lon
    return (lat, lon)

def osm_platforms(rel):
    retval = []
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
    for x in platforms:
        (lat, lon) = osm_member_coord(x)
        name = x.tags.get('ref', '<no ref>')
        desc = x.tags.get('name', '<no name>')
        retval.append([float(lat),float(lon),name,desc])
    return retval


def osm_stops(rel):
    retval = []
    stops = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "stop"]
    for x in stops:
        (lat, lon) = osm_member_coord(x)
        name = x.tags.get('ref', '<no ref>')
        desc = x.tags.get('name', '<no name>')
        retval.append([float(lat),float(lon),name,desc])
    return retval


def route2gpx(rel, fname):
    """Write a gpx-file fname from an overpy relation containing
    an OSM public_transport:version=2 route."""
    latlon = osm_shape(rel)[0]
    waypts = osm_platforms(rel)
    write_gpx(latlon, fname, waypoints=waypts)


def ndist2(n1, n2):
    """Return distance metric squared for two nodes n1 and n2."""
    return (n1.lat - n2.lat)**2 + (n1.lon - n2.lon)**2




def osm_rel(relno):
    rr = api.query("rel(id:%d);(._;>;>;);out body;" % (relno))
    return rr.relations[0]


def osm_rels_v2(lineref, mode="bus"):
    """Get public transport v2 lines corresponding to lineref in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"]["public_transport:version"="2"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr.relations


def osm_rels(lineref, mode="bus"):
    """Get all bus lines corresponding to lineref in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr.relations


def osm2gpx(lineref, mode="bus"):
    rels = osm_rels_v2(lineref, mode)
    if len(rels) > 0:
        for i in range(len(rels)):
            fn = "%s_osm_%d.gpx" % (lineref, i)
            route2gpx(rels[i], fn)
            print(fn)
    else:
        print("Line '%s' not found in OSM PTv2 relations." % lineref)

# Comparison between OSM and HSL data

def test_tag(ts, key, value=None, badtag=False):
    """Test if a tag has a given value or just exists, if value=None."""
    if not key in ts.keys():
        if badtag:
            return
        print("Tag '''%s''' not set " % key, end='')
        if value is not None:
            print("(should be '%s').\n" % value)
        else:
            print(".\n")
        return
    tval = ts[key]
    if badtag:
        print("Probably '''mispelled''' tag '''%s''' with value '%s'.\n" \
          % (key, tval))
        return
    if value is None:
        return
    if tval != value:
        print("Tag '''%s''' has value '%s' (should be '%s').\n" \
          % (key, tval, value))


def test_hsl_routename(ts, lineref, longname):
    """Do a special test for the route name-tag."""
    # First, replace hyphens in know stop names and split and replace back
    # to get a stop list from HSL longName.
    # Match list from gtfs stops.txt:
    # csvtool namedcol "stop_name" stops.txt | grep -o '.*-[[:upper:]]...' | sort -u | tr '\n' '|'
    pat = "Ala-Malm|Ala-Souk|Ala-Tikk|Etelä-Kask|Etelä-Viin|Helsinki-Vant|Itä-Hakk|Kala-Matt|Kallio-Kuni|Koivu-Mank|Lill-Beng|Meri-Rast|Övre-Juss|Pohjois-Haag|Pohjois-Viin|S-Mark|Stor-Kvis|Stor-Rösi|Taka-Niip|Ukko-Pekk|Vanha-Mank|Vanha-Sten|Ylä-Souk|Yli-Finn|Yli-Juss"
    subf = lambda m: m.group().replace('-', '☺')
    stops = re.sub(pat, subf, longname).split('-')
    stops = [s.replace('☺', '-').strip() for s in stops]
    name1 = lineref + " " + "–".join(stops) # Use en dash as a separator
    stops.reverse()
    name2 = lineref + " " + "–".join(stops)
    tag = ts.get("name", "")
    if tag == "":
        print("Tag '''name''' not set (should be either '%s' or '%s').\n" \
          % (name1, name2))
    elif tag != name1 and tag != name2:
        print("Tag '''name''' has value '%s' (should be either '%s' or '%s').\n" \
          % (tag, name1, name2))


def test_route_master(lineref, route_ids, mode="bus"):
    """Test if a route_master relation for lineref exists and contains the
    given route_ids."""
    q = '[out:json][timeout:25];(%s);(rel(br)["type"="route_master"]);out body;' \
      % (";".join(["rel(%d)" % x for x in route_ids]))
    rr = api.query(q)
    nr = len(rr.relations)
    print("'''Route master:'''")
    if nr < 1:
        print("No route_master relation found.\n")
        return
    elif nr == 1:
        rel = rr.relations[0]
        print("Relation: [%s %s]\n" % (osm_relid2url(rel.id), rel.id))
    elif nr > 1:
        print("More than one route_master relations found: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm_relid2url(r.id), r.id) for r in rr.relations)))
        return
    memrefs = [m.ref for m in rel.members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        print("route_master has extra members: %s\n" % (", ".join("[%s %s]" \
          % (osm_relid2url(r.id), r.id) for r in refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        print("Found matching routes not in route_master: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm_relid2url(r.id), r.id) for r in routes_not_in_refs)))
    tags = rr.relations[0].tags
    test_tag(tags, "route_master", mode)
    test_tag(tags, "ref", lineref)
    test_tag(tags, "name")
    test_tag(tags, "network", "HSL")
    #test_tag(tags, "operator")

    print("")


def test_osm_shapes_have_v1_roles(rels):
    """Return True any of the relations in rels contain members with
    'forward' or 'backward' roles."""
    return any(mem.role == 'forward' or mem.role == 'backward'
        for r in rels for mem in r.members)


def test_stop_positions(rel, mode="bus"):
    print("'''Stop positions:'''\n")
    stops = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "stop"]
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
#    print("Route [%s %s] '%s' " % (osm_relid2url(rel.id), rel.id, \
#      rel.tags.get("name", "<no-name-tag>")))
    print("%d stop_positions vs. %d platforms." \
      % (len(stops), len(platforms)))
    print("")
#    # FIXME: Output something sensible
#    for s in stops:
#        test_tag(s.tags, "ref")
#        test_tag(s.tags, "name")
#        test_tag(s.tags, "public_transport", "stop_position")
#        test_tag(s.tags, mode, "yes")
#    for p in platforms:
#        p_name = p.tags.get("name", "<platform-has-no-name>")
#        p_ref = p.tags.get("ref", "<platform-has-no-ref>")
#        refmatches = [s for s in stops \
#          if s.tags.get("ref", "") == p_ref]
#        namematches = [s for s in stops \
#          if s.tags.get("name", "") == p_name]
#        sout = " Platform %s %s:" % (p_ref, p_name)
#        linit = len(sout)
#        if len(refmatches) < 1:
#            sout += " No stop_position with matching ref!"
#        elif len(refmatches) > 1:
#            sout +=" More than one stop_position with matching ref!"
#        if len(namematches) < 1:
#            sout += " No stop_position with matching name!"
#        elif len(namematches) > 1:
#            sout += " More than one stop_position with matching name!"
#        if len(sout) > linit:
#            print(sout)
    print("")


def test_stop_locations():
    # start to complain if stop pos is farther than this from HSL platform
    # FIXME: Turn the comparison around and complain about HSL platforms
    # missing stop positions?
    tol = 0.050 # km FIXME: needs to be bigger for mode=subway?
    osmstops = [osm_stops(rel) for rel in rels]
    for r in range(len(osmstops)):
        print("Route '%s'." % (rels[r].tags.get("name", "<no-name-tag>")))
        print("Stops: %d in OSM vs. %d in HSL.\n" \
        % (len(osmstops[r]), len(hslplatforms[r])))
        for i in range(len(osmstops[r])):
            pdists = [haversine(osmstops[r][i][:2], hslplatforms[r][x][:2])
                for x in range(len(hslplatforms[r])) ]
            pind = pdists.index(min(pdists))
            mind = pdists[pind]
            if mind > tol:
                print(" Distance from OSM stop %s to HSL platform %s (%s)" %
                  (osmstops[r][i][2], hslplatforms[r][pind][2], \
                  hslplatforms[r][pind][3], mind*1000, tol*1000))


def ldist2(p1, p2):
    """Return distance metric squared for two latlon pairs."""
    d = (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2
    return d


def interp_shape(s, tol=10):
    """Given shape s defined as a list of latlon pairs, return a new shape
    with at a distance of no more than tol (meters) between points. New
    points are added with linear interpolation."""
    ltol = inv_haversine(tol/1000.0)
    ltol2 = ltol**2
    sout = [s[0]]
    for i in range(len(s)-1):
        d2 = ldist2(s[i], s[i+1])
        if d2 < ltol2:
            sout.append(s[i+1])
            continue
        d = sqrt(d2)
        n = int(d/ltol)+1
        v = [(s[i+1][0] - s[i][0])/float(n), (s[i+1][1] - s[i][1])/float(n)]
        for j in range(1,n):
            sout.append([s[i][0] + float(j)*v[0], s[i][1] + float(j)*v[1]])
        sout.append(s[i+1])
    return sout

# FIXME: Return also maximum deviation of the shape points or other stats.
def test_shape_overlap(s1, s2, tol=10.0, return_list=False):
    """Return the fraction [0...1.0] by which shape s1 overlaps s2 with
    tolerance tol (meters)."""
    p = interp_shape(s2, tol/2.0)
    ltol2 = inv_haversine(tol/2000.0)**2.0
    startm = 0
    overlaps = []
    for s in s1:
        found = False
        for m in list(range(startm, len(p))) + list(range(0, startm)):
            if ldist2(s, p[m]) < ltol2:
                found = True
                startm = m
                break
        if found:
            overlaps.append(1)
        else:
            overlaps.append(0)
    if return_list:
        return overlaps
    else:
        return float(sum(overlaps))/len(s1)

# plot([s[0] for s in hs1], [s[1] for s in hs1], '*-')
# scatter([s[0] for s in s1], [s[1] for s in s1], c=['g' if o == 1 else 'r' for o in ovl])

def match_shapes(shapes1, shapes2):
    """Determine a mapping from one set of shapes to another, based on
    geometry. Return permutation indices for both directions."""
    if len(shapes1) > len(shapes2):
        swap = True
        s1 = shapes2
        s2 = shapes1
    else:
        swap = False
        s1 = shapes1
        s2 = shapes2
    m1to2 = [None]*len(s1)
    m2to1 = [None]*len(s2)
    for i in range(len(s1)):
        if not s1[i]: # Handle empty shape
            m1to2[i] = 0
            break
        mind = 1.0e10
        minind = 0
        cbeg = s1[i][0]
        cend = s1[i][-1]
        for j in range(len(s2)):
            #d = min(ldist2(cbeg, s2[j][0]), ldist2(cend, s2[j][-1]))
            d = ldist2(cbeg, s2[j][0]) + ldist2(cend, s2[j][-1])
            if d < mind:
                mind = d
                minind = j
        m1to2[i] = minind
    for i in range(len(m1to2)):
        m2to1[m1to2[i]] = i
#    if any(v is None for v in m1to2 + m2to1):
#        print("(mapping is not a bijection)")
    if swap:
        return (m2to1, m1to2)
    else:
        return (m1to2, m2to1)


# FIXME: Use templates for output
def compare_line(lineref, mode="bus"):
    """Report on differences between OSM and HSL data for a given line."""
    print("== %s ==" % lineref)
    rels = osm_rels(lineref, mode)
    if(len(rels) < 1):
        print("No route relations found in OSM.")
        return
    allrelids = [r.id for r in rels]
    rels = [r for r in rels \
            if (r.tags.get("public_transport:version", "") == "2") and
                (r.tags.get("network", "") == "HSL"
                or r.tags.get("network", "") == "Helsinki"
                or r.tags.get("network", "") == "Espoo"
                or r.tags.get("network", "") == "Vantaa")]
    relids = [r.id for r in rels]

    test_route_master(lineref, [r.id for r in rels], mode)

#    print("Found OSM route ids: %s\n" % \
#      (", ".join("[%s %d]" % (osm_relid2url(rid), rid) for rid in relids)))
    alsoids = [r for r in allrelids if r not in relids]
    if alsoids:
        print("Extra routes in OSM with the same ref: %s\n" % \
          (", ".join("[%s %d]" % (osm_relid2url(r), r) for r in alsoids)))
    if len(rels) > 2:
        print("More than 2 matching OSM routes found: %s.\n" % \
          (", ".join("[%s %d]" \
            % (osm_relid2url(rid), rid) for rid in relids)))
        print("Giving up.")
        return

    htags = hsl_tags(lineref)
    codes = hsl_patterns_after_date(lineref, \
                datetime.date.today().strftime("%Y%m%d"), mode)
#    print("Found HSL pattern codes: %s\n" %
#        (", ".join("[%s %s]" % (hsl_pattern2url(c), c) for c in codes)))

    # Mapping
    # FIXME: Duplicate call to osm_shape() in route checking loop.
    osmshapes = [osm_shape(rel)[0] for rel in rels]
    hslshapes = [hsl_shape(c)[1] for c in codes]
    (osm2hsl, hsl2osm) = match_shapes(osmshapes, hslshapes)
    id2hslindex = {}
    for i in range(len(relids)):
        id2hslindex[relids[i]] = osm2hsl[i]
    if len(codes) != 2:
        print("%d route pattern(s) in HSL data, matching may be wrong.\n" \
          % (len(codes)))
        for i in range(len(relids)):
            print(" %s -> %s" % \
              (relids[i], "None" if osm2hsl[i] is None else codes[osm2hsl[i]]))
        for i in range(len(codes)):
            print(" %s -> %s" % \
              (codes[i], "None" if hsl2osm[i] is None else relids[hsl2osm[i]]))
    print("")

# Main route checking loop
    for rel in rels:
        print("'''Route [%s %s] %s'''\n" \
          % (osm_relid2url(rel.id), rel.id, rel.tags.get("name", "")))

        print("'''Tags:'''\n")
        # name-tag gets special treatment
        test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"])
        test_tag(rel.tags, "network", "HSL")
        # TODO: infer interval from timetable data
        test_tag(rel.tags, "from")
        test_tag(rel.tags, "to")
        test_tag(rel.tags, "interval")
        test_tag(rel.tags, "colour", hsl_modecolors[mode])
        test_tag(rel.tags, "color", badtag=True)

        hsli = id2hslindex[rel.id]
        #print("Matching HSL pattern %s.\n" % (codes[hsli]))

        if rel.tags.get("public_transport:version", "0") != "2":
            print("Tag public_transport:version=2 not set in OSM route %s. Giving up." % (rel.id))
            continue

        if any(mem.role == 'forward' or mem.role == 'backward'
          for mem in rel.members):
            print("OSM route(s) tagged with public_transport:version=2,")
            print("but have members with 'forward' or 'backward' roles.")
            print("Skipping shape, platform and stop tests.\n")
            continue

        print("'''Shape:'''\n")
        if hsli is not None:
            tol = 30
            (shape, gaps) = osm_shape(rel)
            if gaps:
                print("Route has '''gaps'''!\n")
            ovl = test_shape_overlap(shape, hslshapes[hsli], tol=tol)
            print("Route [%s %s] overlap (tolerance %d m) with HSL pattern [%s %s] is '''%2.1f %%'''.\n" \
              % (osm_relid2url(rel.id), rel.id, tol, hsl_pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
        else:
            print("Route %s overlap could not be calculated.\n" \
              % (rel.id))

        test_stop_positions(rel)

        # Platforms
        print("'''Platforms:'''\n")
        if hsli is not None:
            osmplatform = osm_platforms(rel)
            hslplatform = hsl_platforms(codes[hsli])
            # FIXME: Should add something to the diff list for platforms
            #        missing from OSM.
            osmp = [p[2]+"\n" for p in osmplatform]
            hslp = [p[2]+"\n" for p in hslplatform]
            diff = list(difflib.unified_diff(osmp, hslp, "OSM", "HSL"))
            if diff:
                sys.stdout.writelines(" " + d for d in diff)
            else:
                print(" => Identical platform sequences.\n")
        else:
            print("Platforms could not be compared.")
        print("")


def compare(mode="bus"):
# TODO: Add link to Subway validator at http://osmz.ru/subways/finland.html
# for mode="subway"
    osmdict = osm_all_linerefs(mode)
    hsldict = hsl_all_linerefs(mode)
    osmlines = set(osmdict)
    hsllines = set(hsldict)
    # TODO: Replace HSL with region var everywhere.
    region = "HSL"
    print("= Summary of %s transit in %s region. =" % (mode, region))
    print("%d lines in OSM.\n" % len(osmlines))
    print("%d lines in HSL.\n" % len(hsllines))
    print("")
    sortf = lambda x: (len([c for c in x if c.isdigit()]), x)
    osmextra = list(osmlines.difference(hsllines))
    osmextra.sort(key=sortf)
    print("%d lines in OSM but not in HSL:" % len(osmextra))
    print(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in osmextra ] ))
    print("")
    hslextra = list(hsllines.difference(osmlines))
    hslextra.sort(key=sortf)
    print("%d lines in HSL but not in OSM:" % len(hslextra))
    print(" %s" % ", ".join(["[%s %s]" % (hsldict[x], x) for x in hslextra]))
    print("")
    commons = list(hsllines.intersection(osmlines))
    commons.sort(key=sortf)
    print("%d lines in both HSL and OSM." % len(commons))
    print(" %s." % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in commons] ))
    print("")
    osm2dict = osm_ptv2_linerefs(mode)
    osm2lines = set(osm2dict)
    commons2 = list(hsllines.intersection(osm2lines))
    commons2.sort(key=sortf)
    print("%d lines in both HSL and OSM with public_transport:version=2 tagging.\n" % len(commons2))
    print(" %s." % ", ".join("[[#%s|%s]]" % (s, s) for s in commons2))
    print("")
    print("= Lines =")
    for line in commons2:
        compare_line(line, mode)
        print("")


def sub_gpx(args):
    print("Processing line %s, mode '%s'" % (args.line, args.mode))
    osm2gpx(args.line, args.mode)
    hsl2gpx(args.line, args.mode)


def sub_line(args):
    line = args.line
    mode = args.mode
    compare_line(line, mode)


def sub_report(args):
    compare(mode=args.mode)


def sub_fullreport(args):
    pass


# TODO: Add sub_stops(args) for creating a report on stops
# List of stop code prefixes from gtfs:
# csvtool namedcol stop_code stops.txt| tail -n+2 | grep -o '^[^0-9]*' | sort -u
# TODO: Test ref:findr tag on stops test_tag(rel.tags, "ref:findr")

if __name__ == '__main__' and '__file__' in globals ():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', '-v', action='version', version='0.0.1')
    parser.set_defaults(func=lambda _: print(parser.format_usage()))
    subparsers = parser.add_subparsers(help='sub-command -h for help')
    parser_gpx = subparsers.add_parser('gpx', help='Output gpx files for given line.')
    parser_gpx.add_argument('line', metavar='<lineid>',
        help='Line id to process.')
    parser_gpx.add_argument('mode', nargs='?', metavar='<mode>', default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_gpx.set_defaults(func=sub_gpx)

    parser_line = subparsers.add_parser('line', help='Create a report for a given line.')
    parser_line.add_argument('line', metavar='<lineid>',
        help='Line id to report on.')
    parser_line.add_argument('mode', nargs='?', metavar='<mode>', default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_line.set_defaults(func=sub_line)

    parser_report = subparsers.add_parser('report',
        help='Report on all lines for a given mode.')
    parser_report.add_argument('mode', nargs='?', metavar='<mode>', default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_report.set_defaults(func=sub_report)

    parser_fullreport = subparsers.add_parser('fullreport',
        help='Create a report for all lines.')
    parser_fullreport.set_defaults(func=sub_fullreport)

    args = parser.parse_args()
    #sys.exit(1)
    args.func(args)
