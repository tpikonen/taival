#!/usr/bin/env python3
import sys, datetime, gpxpy.gpx, overpy, argparse, requests, json, difflib, re
import logging
import digitransit
from collections import defaultdict
from math import radians, degrees, cos, sin, asin, sqrt

hsl_modecolors = { "bus": "#007AC9",
    "tram":     "#00985F",
    "train":    "#8C4799",
    "subway":   "#FF6319",
    "ferry":    "#00B9E4",
    "aerialway": None,
    "monorail": None,
    "trolleybus": None
}
hsl_peakhours = [(7, 9), (15,18)]
# HSL night services start at 23, but use midnight to avoid overlap with
# normal services.
hsl_nighthours = [(0, 5)]
hsl = digitransit.Digitransit("HSL", \
        "https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql", \
        hsl_modecolors, hsl_peakhours, hsl_nighthours)

logging.basicConfig(level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

log = logging.getLogger(__name__)


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


def digitransit2gpx(dt, lineref, mode="bus"):
    """Write gpx files for given lineref from digitransit API data."""
    log.debug("Calling dt.codes")
    codes = dt.codes(lineref, mode)
    for c in codes:
        log.debug("    Calling dt.shape")
        (dirid, latlon) = dt.shape(c)
        log.debug("    Calling dt.platforms")
        stops = dt.platforms(c)
        fname = "%s_%s_%s_%d.gpx" % (lineref, dt.agency, c, dirid)
        write_gpx(latlon, fname, waypoints=stops)
        print(fname)
    if not codes:
        log.error("Line '%s' not found in %s." % lineref, dt.agency)


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
api.retry_timeout=120
api.max_retry_count=10
# Approximate HSL area = Helsinki + Porvoo regions
area = """(area[admin_level=7]["name"="Helsingin seutukunta"]["ref"="011"][boundary=administrative]; area[admin_level=7]["name"="Porvoon seutukunta"]["ref"="201"][boundary=administrative];)->.hel;"""


def osm_relid2url(relid):
    return "https://www.openstreetmap.org/relation/" + str(relid)


def osm_all_linerefs(mode="bus"):
    """Return a lineref:[urllist] dict of all linerefs in Helsinki region.
    URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[type=route][route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
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


def osm_was_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all was:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[type="was:route"]["was:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(osm_relid2url(r.id))
    return refs


def osm_disused_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all disused:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[type="disused:route"]["disused:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(osm_relid2url(r.id))
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
        # Determine correct orientation for a single way route
        stops = [mem.resolve() for mem in rel.members if mem.role == "stop"]
        if stops:
            spos = osm_member_coord(stops[0])
            if ldist2(spos, latlon[0]) > ldist2(spos, latlon[-1]):
                latlon.reverse()
            return (latlon, gaps)
        plats = [mem.resolve() for mem in rel.members if mem.role == "platform"]
        if plats:
            ppos = osm_member_coord(plats[0])
            if ldist2(ppos, latlon[0]) > ldist2(ppos, latlon[-1]):
                latlon.reverse()
            return (latlon, gaps)
        # Give up and do not orient
        return (latlon, gaps)
    # Initialize nodes list with first way, correctly oriented
    if (ways[0].nodes[-1] == ways[1].nodes[0]) \
      or (ways[0].nodes[-1] == ways[1].nodes[-1]):
        nodes = ways[0].nodes
    elif (ways[0].nodes[0] == ways[1].nodes[0]) \
      or (ways[0].nodes[0] == ways[1].nodes[-1]):
        nodes = ways[0].nodes[::-1] # reverse
    else:
        # Gap between first two ways
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
            # Gap between ways
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
        lat = float(x.lat)
        lon = float(x.lon)
    return (lat, lon)


def osm_platforms(rel):
    retval = []
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
    for x in platforms:
        (lat, lon) = osm_member_coord(x)
        ref = x.tags.get('ref', '<no ref in OSM>')
        name = x.tags.get('name', '<no name in OSM>')
        retval.append([float(lat),float(lon),ref,name])
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


def osm_stops_by_refs(refs, mode="bus"):
    """Return a list of OSM node ids which have one of the 'ref' tag values in
    a given refs list."""
    # FIXME: This does not really work with all the tagging conventions in OSM
    mode2stoptag = {
        "train" : None,
        "subway" : None,
        "tram" : '''"railway"="tram_stop"''',
        "bus" : '''"highway"="bus_stop"''',
        "ferry" : '''"amenity="ferry_terminal"'''
    }
    q = '%s node(area.hel)[%s][ref~"(%s)"];out tags;' \
        % (area, mode2stoptag[mode], "|".join(str(r) for r in refs))
    rr = api.query(q)
    stopids = []
    for ref in refs:
        stopids.extend(n.id for n in rr.nodes if n.tags["ref"] == ref)
    return stopids


def route2gpx(rel, fname):
    """Write a gpx-file fname from an overpy relation containing
    an OSM public_transport:version=2 route."""
    log.debug("Calling osm_shape")
    latlon = osm_shape(rel)[0]
    log.debug("Calling osm_platforms")
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
    """Get all lines corresponding to lineref and mode in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr.relations


def osm2gpx(lineref, mode="bus"):
    log.debug("Calling osm_rels_v2")
    rels = osm_rels_v2(lineref, mode)
    if len(rels) > 0:
        for i in range(len(rels)):
            fn = "%s_osm_%d.gpx" % (lineref, i)
            route2gpx(rels[i], fn)
            print(fn)
    else:
        log.error("Line '%s' not found in OSM PTv2 relations." % lineref)

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


def hsl_longname2stops(longname):
    # First, replace hyphens in know stop names and split and replace back
    # to get a stop list from HSL longName.
    # Match list from gtfs stops.txt:
    # csvtool namedcol "stop_name" stops.txt | grep -o '.*-[[:upper:]]...' | sort -u | tr '\n' '|'
    pat = "Ala-Malm|Ala-Souk|Ala-Tikk|Etelä-Kask|Etelä-Viin|Helsinki-Vant|Itä-Hakk|Kala-Matt|Kallio-Kuni|Koivu-Mank|Lill-Beng|Meri-Rast|Övre-Juss|Pohjois-Haag|Pohjois-Viin|S-Mark|Stor-Kvis|Stor-Rösi|Taka-Niip|Ukko-Pekk|Vanha-Mank|Vanha-Sten|Ylä-Souk|Yli-Finn|Yli-Juss"
    # Other place names with hyphens
    extrapat="|Pohjois-Nikinmä|Länsi-Pasila"
    pat = pat + extrapat
    subf = lambda m: m.group().replace('-', '☺')
    stops = re.sub(pat, subf, longname).split('-')
    stops = [s.replace('☺', '-').strip() for s in stops]
    return stops


def test_hsl_routename(ts, lineref, longname):
    """Do a special test for the route name-tag."""
    stops = hsl_longname2stops(longname)
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


def arrivals2intervals(arrivals, peakhours=None, nighthours=None):
    """Service intervals in minutes from daily arrivals to a stop given in
    seconds since midnight. Returns a tuple of three sorted interval lists
    (normal, peak, night). 'peak' or 'night' are None if peakhours or
    nighthours are not given."""
    if peakhours:
        peak = [(3600*h[0], 3600*h[1]) for h in peakhours]
    else:
        peak = None
    if nighthours:
        night = [(3600*h[0], 3600*h[1]) for h in nighthours]
    else:
        night = None
    inorms = []
    ipeaks = []
    inights = []
    for i in range(len(arrivals)-1):
        ival = (arrivals[i+1] - arrivals[i]) // 60
        # Correct for times > 24 * 60 * 60 s
        tval = arrivals[i] if arrivals[i] < 24*3600 else arrivals[i] - 24*3600
        if peak and any(tval >= h[0] and tval <= h[1] for h in peak):
            ipeaks.append(ival)
        elif night and any(tval >= h[0] and tval <= h[1] for h in night):
            inights.append(ival)
        else:
            inorms.append(ival)
    inorms.sort()
    ipeaks.sort()
    inights.sort()
    #print("inorms: %s" % (str(inorms)))
    #print("ipeaks: %s" % (str(ipeaks)))
    #print("inights: %s" % (str(inights)))
    return (inorms, ipeaks, inights)


def test_interval_tags(reltags, code):
    """Determine interval tags for peak and normal hours for weekdays (monday),
    saturday and sunday from arrival data. Compare to existing tags."""
    # Get interval tags from API
    today = datetime.date.today()
    delta = (5 + 7 - today.weekday()) % 7 # Days to next saturday
    tags = {}
    daynames = ["saturday", "sunday", None] # weekdays (monday) is the default
    for i in range(3):
        day = (today + datetime.timedelta(days=delta+i)).strftime("%Y%m%d")
        (norm, peak, night) = arrivals2intervals(\
            hsl.arrivals_for_date(code, day), hsl.peakhours, hsl.nighthours)
        tagname = "interval" + (":" + daynames[i] if daynames[i] else "")
        if (len(norm) + len(peak) + len(night)) == 0:
            tags[tagname] = "no_service"
        else:
            # FIXME: Maybe combine norm and peak if peak is short enough?
            # Only tag if there are more than 2 intervals, i.e.
            # at least 3 arrivals in a period.
            if len(norm) > 1:
                med_norm = norm[len(norm)//2]
                tags[tagname] = str(med_norm)
                if len(peak) > 1:
                    med_peak = peak[len(peak)//2]
                    # Only add interval:peak tag if it's significantly smaller.
                    if med_peak <= 0.8* med_norm:
                        tags[tagname + ":peak"] = str(med_peak)
            if len(night) > 1:
                tags[tagname + ":night"] = str(night[len(night)//2])
                if not norm:
                    tags[tagname] = "no_service"
    itmp = tags.get("interval", "1")
    interval = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:saturday", "1")
    isat = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:sunday", "1")
    isun = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:night", "1")
    inight = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:saturday:night", "1")
    isatnight = int(itmp) if itmp.isdigit() else 1
    itmp = tags.get("interval:sunday:night", "1")
    isunnight = int(itmp) if itmp.isdigit() else 1
    # Remove weekend tags if they are not significantly different
    if abs(isat - interval)/interval < 0.2 \
      and tags.get("interval:saturday", "") != "no_service":
        tags.pop("interval:saturday", 0)
        tags.pop("interval:saturday:peak", 0)
    if abs(isun - interval)/interval < 0.2 \
      and tags.get("interval:sunday", "") != "no_service":
        tags.pop("interval:sunday", 0)
        tags.pop("interval:sunday:peak", 0)
    if abs(isatnight - inight)/inight < 0.2 \
      and tags.get("interval:saturday:night", "") != "no_service":
        tags.pop("interval:saturday:night", 0)
    if abs(isunnight - inight)/inight < 0.2 \
      and tags.get("interval:sunday:night", "") != "no_service":
        tags.pop("interval:sunday:night", 0)
    # Compare to existing tags
    for k in sorted(tags.keys()):
        test_tag(reltags, k, tags[k])


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


def collect_route_master(ld, route_ids):
    """Get route master relation from Overpass"""
    lineref = ld["lineref"]
    mode = ld["mode"]
    q = '[out:json][timeout:60];(%s);(rel(br)["type"="route_master"];);out body;' \
      % ("".join(["rel(%d);" % x for x in route_ids]))
    rr = api.query(q)
    ld["rm_rels"] = rr.relations
    return ld


def print_route_master(ld):
    """Test if a route_master relation for lineref exists and contains the
    given route_ids."""
    lineref = ld["lineref"]
    mode = ld["mode"]
    rm_rels = ld["rm_rels"]
    route_ids = [r.id for r in ld["rels"]]

    nr = len(rm_rels)
    print("'''Route master:'''")
    if nr < 1:
        print("No route_master relation found.\n")
        return
    elif nr > 1:
        print("More than one route_master relations found: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm_relid2url(r.id), r.id) for r in rm_rels)))
        return
    elif nr == 1:
        rel = rm_rels[0]
        print("Relation: [%s %s]\n" % (osm_relid2url(rel.id), rel.id))
    memrefs = [m.ref for m in rel.members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        print("route_master has extra members: %s\n" % (", ".join("[%s %s]" \
          % (osm_relid2url(r), r) for r in refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        print("Found matching routes not in route_master: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm_relid2url(r), r) for r in routes_not_in_refs)))
    tags = rel.tags
    test_tag(tags, "route_master", mode)
    test_tag(tags, "ref", lineref)
    test_tag(tags, "name")
    test_tag(tags, "network", "HSL")
    #test_tag(tags, "operator")

    print("")


# FIXME: Use templates for output
def print_linedict(ld):
    """Print a info from a line dict from collect_line()"""
    lineref = ld["lineref"]
    mode = ld["mode"]
    print("== %s ==" % lineref)
    rels = ld["rels"]
    if(len(rels) < 1):
        print("No route relations found in OSM.")
        return
    relids = [r.id for r in rels]

    print_route_master(ld)

    alsoids = ld["alsoids"]
    if alsoids:
        print("Extra routes in OSM with the same ref: %s\n" % \
          (", ".join("[%s %d]" % (osm_relid2url(r), r) for r in alsoids)))
    if len(rels) > 2:
        print("More than 2 matching OSM routes found: %s.\n" % \
          (", ".join("[%s %d]" \
            % (osm_relid2url(rid), rid) for rid in relids)))
        print("Giving up.")
        return
    codes = ld["codes"]
    osm2hsl = ld["osm2hsl"]
    hsl2osm = ld["hsl2osm"]
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

    id2hslindex = ld["id2hslindex"]
    htags = ld["htags"]
    interval_tags = ld["interval_tags"]
    hslshapes = ld["hslshapes"]
    for rel in rels:
        print("'''Route [%s %s] %s'''\n" \
          % (osm_relid2url(rel.id), rel.id, rel.tags.get("name", "")))
        hsli = id2hslindex[rel.id]

        print("'''Tags:'''\n")
        # name-tag gets a special treatment
        test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"])
        # FIXME: network != agency always
        test_tag(rel.tags, "network", hsl.agency)
        test_tag(rel.tags, "from")
        test_tag(rel.tags, "to")
        if hsl.modecolors[mode]:
            test_tag(rel.tags, "colour", hsl.modecolors[mode])
        test_tag(rel.tags, "color", badtag=True)
        if hsli is not None and interval_tags:
            test_interval_tags(rel.tags, codes[hsli])

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
              % (osm_relid2url(rel.id), rel.id, tol, hsl.pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
        else:
            print("Route %s overlap could not be calculated.\n" \
              % (rel.id))

        test_stop_positions(rel)

        hsli = id2hslindex[rel.id]
        # Platforms
        print("'''Platforms:'''\n")
        hslplatforms = ld["hslplatforms"]
        if hsli is not None:
            osmplatform = osm_platforms(rel)
            hslplatform = hslplatforms[hsli]
            # FIXME: Add stop names to unified diffs after diffing, somehow
            #osmp = [p[2]+" "+p[3]+"\n" for p in osmplatform]
            #hslp = [str(p[2])+" "+str(p[3])+"\n" for p in hslplatform]
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


def collect_line(lineref, mode="bus", interval_tags=False):
    """Report on differences between OSM and HSL data for a given line."""
    ld = {} # line dict
    ld["lineref"] = lineref
    ld["mode"] = mode
    ld["interval_tags"] = interval_tags
    log.debug("Calling osm_rels")
    rels = osm_rels(lineref, mode)
    if(len(rels) < 1):
        log.debug("No route relations found in OSM.")
        return ld
    allrelids = [r.id for r in rels]
    rels = [r for r in rels \
            if (r.tags.get("public_transport:version", "") == "2") and
                (r.tags.get("network", "") == "HSL"
                or r.tags.get("network", "") == "Helsinki"
                or r.tags.get("network", "") == "Espoo"
                or r.tags.get("network", "") == "Vantaa")]
    relids = [r.id for r in rels]
    ld["rels"] = rels

    # TODO: convert
    log.debug("Calling collect_route_master")
    collect_route_master(ld, relids)

    log.debug("Found OSM route ids: %s\n" % \
      (", ".join("[%s %d]" % (osm_relid2url(rid), rid) for rid in relids)))
    alsoids = [r for r in allrelids if r not in relids]
    ld["alsoids"] = alsoids

    htags = hsl.tags(lineref)
    ld["htags"] = htags
#    codes = hsl.codes_after_date(lineref, \
#                datetime.date.today().strftime("%Y%m%d"), mode)
#    codes = hsl.codes_longest_per_direction(lineref, mode)
    codes = hsl.codes_longest_after_date(lineref, \
                datetime.date.today().strftime("%Y%m%d"), mode)
    ld["codes"] = codes
    log.debug("Found HSL pattern codes: %s\n" %
        (", ".join("[%s %s]" % (hsl.pattern2url(c), c) for c in codes)))
#    # Use just the ':01' route variant
#    cfilt = [c for c in codes if (len(c) - c.rfind(":01")) == 3]
#    if len(cfilt) >= len(rels):
#        codes = cfilt
#        log.debug("Using just first route variants: %s\n" % (str(codes)))

    # Mapping
    # FIXME: Duplicate call to osm_shape() in route checking loop.
    osmshapes = [osm_shape(rel)[0] for rel in rels]
    hslshapes = [hsl.shape(c)[1] for c in codes]
    (osm2hsl, hsl2osm) = match_shapes(osmshapes, hslshapes)
    id2hslindex = {}
    for i in range(len(relids)):
        id2hslindex[relids[i]] = osm2hsl[i]
    ld["osmshapes"] = osmshapes
    ld["hslshapes"] = hslshapes
    ld["id2hslindex"] = id2hslindex
    ld["osm2hsl"] = osm2hsl
    ld["hsl2osm"] = hsl2osm
    # Fill hslplatforms only for pattern codes which match OSM route
    hslplatforms = [None]*len(codes)
    for rel in rels:
        hsli = id2hslindex[rel.id]
        if hsli is not None:
            hslplatforms[hsli] = [ p if p[2] else (p[0],p[1],"<no ref in HSL>",p[3])
                for p in hsl.platforms(codes[hsli]) ]
    ld["hslplatforms"] = hslplatforms
    return ld


def compare(mode="bus", interval_tags=False):
# TODO: Add link to Subway validator at http://osmz.ru/subways/finland.html
# for mode="subway"
    osmdict = osm_all_linerefs(mode)
    hsldict = hsl.all_linerefs(mode)
    hsl_localbus = hsl.taxibus_linerefs(mode)
    osmlines = set(osmdict)
    hsllines = set(hsldict)
    hsl_locallines = set(hsl_localbus)
    # TODO: Replace HSL with agency var everywhere.
    agency = "HSL"
    agencyurl = "https://www.hsl.fi/"
    print("This is a comparison of OSM public transit route data with [%s %s] %s transit data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n" % (agencyurl, agency, mode))
    print("= Summary of %s transit in %s region. =" % (mode, agency))
    print("%d lines in OSM.\n" % len(osmlines))
    print("%d lines in HSL.\n" % len(hsllines))
    print("")
    sortf = lambda x: (len([c for c in x if c.isdigit()]), x)
    osmextra = osmlines.difference(hsllines)
    osmextra = list(osmextra.difference(hsl_locallines))
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
    print(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in commons] ))
    print("")
    osm2dict = osm_ptv2_linerefs(mode)
    osm2lines = set(osm2dict)
    commons2 = list(hsllines.intersection(osm2lines))
    commons2.sort(key=sortf)
    print("%d lines in both HSL and OSM with public_transport:version=2 tagging.\n" % len(commons2))
    print(" %s" % ", ".join("[[#%s|%s]]" % (s, s) for s in commons2))
    print("")
    if mode == "bus":
        lbuses = list(hsl_locallines)
        lbuses.sort(key=sortf)
        print("= Local bus lines =")
        print("%d bus routes with GTFS type 704 (lähibussi) in HSL." \
            % (len(lbuses)))
        print(" %s" % ", ".join(["[%s %s]" % (hsl_localbus[x], x) \
            for x in lbuses] ))
        print("")
        lcommons = list(hsl_locallines.intersection(osmlines))
        lcommons.sort(key=sortf)
        print("%d normal bus routes in OSM with HSL local bus route number." \
            % (len(lcommons)))
        print(" %s" % ", ".join(["%s (%s)" % \
            (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
                for z in range(len(osmdict[x]))])) for x in lcommons ] ))
        print("")
        osm_minibusdict = osm_all_linerefs(mode="minibus")
        osm_minibuslines = list(osm_minibusdict)
        osm_minibuslines.sort(key=sortf)
        print("%d route=minibus routes in OSM." % (len(osm_minibuslines)))
        print(" %s" % ", ".join(["%s (%s)" % \
            (x, ", ".join(["[%s %d]" % (osm_minibusdict[x][z], z+1) \
                for z in range(len(osm_minibusdict[x]))])) \
                for x in osm_minibuslines ] ))
        print("")
    print("= Old lines =")
    wasroutes = osm_was_routes(mode)
    waslines = list(wasroutes)
    waslines.sort(key=sortf)
    print("%d routes with type 'was:route=%s'." % (len(wasroutes), mode))
    print(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (wasroutes[x][z], z+1) \
            for z in range(len(wasroutes[x]))])) for x in waslines] ))
    print("")
    disroutes = osm_disused_routes(mode)
    dislines = list(disroutes)
    dislines.sort(key=sortf)
    print("%d routes with type 'disused:route=%s'." % (len(disroutes), mode))
    print(" %s" % ", ".join(["%s (%s)" % \
        (x, ", ".join(["[%s %d]" % (disroutes[x][z], z+1) \
            for z in range(len(disroutes[x]))])) for x in dislines] ))
    print("")
    print("= Lines =")
    for line in commons2:
        ld = collect_line(line, mode, interval_tags)
        print_linedict(ld)
        print("")


def sub_gpx(args):
    log.info("Processing line %s, mode '%s'" % (args.line, args.mode))
    osm2gpx(args.line, args.mode)
    digitransit2gpx(hsl, args.line, args.mode)


def sub_osmxml(args):

    def write_xml(fname, ids, htags, mode, reverse=False):
        with open(fname, "w") as ff:
            for i in ids:
                ff.write("    <member type='node' ref='%d' role='platform' />\n" % i)
            stopnames = hsl_longname2stops(htags["longName"])
            if reverse:
                stopnames.reverse()
            ff.write("    <tag k='name' v='%s' />\n" \
                % (htags["shortName"] + " " + "–".join(stopnames)))
            ff.write("    <tag k='ref' v='%s' />\n" % htags["shortName"])
            ff.write("    <tag k='network' v='HSL' />\n")
            ff.write("    <tag k='route' v='%s' />\n" % mode)
            ff.write("    <tag k='type' v='route' />\n")
            ff.write("    <tag k='public_transport:version' v='2' />\n")

    log.info("Processing line %s, mode '%s'" % (args.line, args.mode))
    log.debug("Calling hsl.codes")
    codes = hsl.codes(args.line, args.mode)
    log.debug("Calling hsl.tags")
    htags = hsl.tags(args.line)
    for c in codes:
        log.debug("Pattern code %s" % c)
        # reverse stops string if direction code is odd
        reverse = (int(c.split(":")[2]) % 2) == 1
        log.debug("   Calling hsl.platforms")
        stops = [p[2] for p in hsl.platforms(c)]
        fname = "%s_%s_%s.osm" % (args.line, hsl.agency, c)
        log.debug("   Calling osm_stops_by_refs")
        ids = osm_stops_by_refs(stops, args.mode)
        write_xml(fname, ids, htags, args.mode, reverse)
        print(fname)
    if not codes:
        print("Line '%s' not found in %s." % lineref, hsl.agency)


def sub_line(args):
    print_linedict(collect_line(args.line, args.mode, args.interval_tags))


def sub_report(args):
    compare(mode=args.mode, interval_tags=args.interval_tags)


#def sub_fullreport(args):
#    pass


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

    parser_osmxml = subparsers.add_parser('osmxml', help='Output OSM XML snippets with stops and some tags for a given line.')
    parser_osmxml.add_argument('line', metavar='<lineid>',
        help='Line id to process.')
    parser_osmxml.add_argument('mode', nargs='?', metavar='<mode>',
        default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_osmxml.set_defaults(func=sub_osmxml)

    parser_line = subparsers.add_parser('line', help='Create a report for a given line.')
    parser_line.add_argument('--interval-tags', '-i', action='store_true',
        dest='interval_tags', help='Also report on "interval*" tags')
    parser_line.add_argument('line', metavar='<lineid>',
        help='Line id to report on.')
    parser_line.add_argument('mode', nargs='?', metavar='<mode>', default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_line.set_defaults(func=sub_line)

    parser_report = subparsers.add_parser('report',
        help='Report on all lines for a given mode.')
    parser_report.add_argument('--interval-tags', '-i', action='store_true',
        dest='interval_tags', help='Also report on "interval*" tags')
    parser_report.add_argument('mode', nargs='?', metavar='<mode>',
        default="bus",
        help='Transport mode: train, subway, tram, bus (default) or ferry')
    parser_report.set_defaults(func=sub_report)

#    parser_fullreport = subparsers.add_parser('fullreport',
#        help='Create a report for all lines.')
#    parser_fullreport.set_defaults(func=sub_fullreport)

    args = parser.parse_args()
    #sys.exit(1)
    args.func(args)
