import overpy, logging
from collections import defaultdict
from util import ldist2

log = logging.getLogger(__name__)

api = overpy.Overpass()
api.retry_timeout=12
api.max_retry_count=10
# Approximate HSL area = Helsinki + Porvoo regions
#area = """(area[admin_level=7]["name"="Helsingin seutukunta"]["ref"="011"][boundary=administrative]; area[admin_level=7]["name"="Porvoon seutukunta"]["ref"="201"][boundary=administrative];)->.hel;"""
area = None

stoptags = {
    "train": [
        { "railway": "station" },
        { "railway": "halt" },
        { "railway": "platform" },
        { "railway": "platform_edge" } ],
    "light_rail": [
        { "railway": "station",         "station": "light_rail" },
        { "railway": "halt",            "light_rail": "yes" },
        { "railway": "platform",        "light_rail": "yes" },
        { "railway": "platform_edge",   "light_rail": "yes" } ],
    "subway": [
        { "railway": "station",         "station": "subway" },
        { "railway": "halt",            "subway": "yes" },
        { "railway": "platform",        "subway": "yes" },
        { "railway": "platform_edge",   "subway": "yes" } ],
    "monorail": [
        { "railway": "station",         "station": "monorail" },
        { "railway": "halt",            "monorail": "yes" },
        { "railway": "platform",        "monorail": "yes" },
        { "railway": "platform_edge",   "monorail": "yes" } ],
    "tram": [
        { "railway": "tram_stop" } ],
    "bus": [
        { "amenity": "bus_station" },
        { "highway": "bus_stop" } ],
    "trolleybus": [
        { "amenity": "bus_station", "trolleybus": "yes" },
        { "highway": "bus_stop", "trolleybus": "yes" } ],
    "ferry": [
        { "amenity": "ferry_terminal" } ],
    "aerialway": [
        { "aerialway": "station" } ],
}

citybiketags = [ { "amenity": "bicycle_rental" } ]

bikeparktags = [ { "amenity": "bicycle_parking" } ]


def stoptags2mode(otags):
    """Return a list of mode strings which correspond to OSM tags."""
    outl = []
    for mode, mtaglist in stoptags.items():
        match = False
        for mtags in mtaglist:
            so_far_ok = True
            for k, v in mtags.items():
                if (not k in otags.keys()) or otags[k] != v:
                    so_far_ok = False
                    break
            if so_far_ok:
                match = True
                break
        if match:
            outl.append(mode)
    # train always matches also subway and monorail tags
    if "train" in outl and ("subway" in outl or "monorail" in outl):
        outl.remove("train")
    return outl


def mode2ovpstoptags(mode):
    """Return a list of Overpass tag filters."""
    tlist = stoptags[mode]
    out = []
    for tags in tlist:
        out.append(''.join([ '["{}"="{}"]'.format(k, v) for k, v in tags.items() ]))
    return out


def relid2url(relid):
    return "https://www.openstreetmap.org/relation/" + str(relid)


def all_linerefs(mode="bus"):
    """Return a lineref:[urllist] dict of all linerefs in Helsinki region.
    URLs points to the relations in OSM."""
    q = '%s\nrel(area.hel)[type=route][route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    log.debug(q)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    #refs = {r.tags["ref"]:relid2url(r.id)
    #        for r in rr.relations if "ref" in r.tags.keys()}
    return refs


def ptv2_linerefs(mode="bus"):
    """Return a lineref:url dict of linerefs with public_transport:version=2
    tag in Helsinki region.
    URL points to the relation in OSM."""
    q = '%s\nrel(area.hel)[route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"]["public_transport:version"="2"];out tags;' % (area, mode)
    log.debug(q)
    rr = api.query(q)
    refs = {r.tags["ref"]:relid2url(r.id)
            for r in rr.relations if "ref" in r.tags.keys()}
    return refs


def was_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all was:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '%s\nrel(area.hel)[type="was:route"]["was:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    log.debug(q)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs


def disused_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all disused:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '%s\nrel(area.hel)[type="disused:route"]["disused:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    log.debug(q)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs


def route_master(route_ids):
    """Get route master relation from Overpass"""
    # FIXME: Use 'rel(id:%s)'.join(...) below
    q = '[out:json][timeout:60];rel(id:%s);(rel(br)["type"="route_master"];);out body;' \
      % (",".join(str(x) for x in route_ids))
    log.debug(q)
    rr = api.query(q)
    return rr.relations


def ndist2(n1, n2):
    """Return distance metric squared for two nodes n1 and n2."""
    return (n1.lat - n2.lat)**2 + (n1.lon - n2.lon)**2


def route_shape(rel):
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
            spos = member_coord(stops[0])
            if ldist2(spos, latlon[0]) > ldist2(spos, latlon[-1]):
                latlon.reverse()
            return (latlon, gaps)
        plats = [mem.resolve() for mem in rel.members if mem.role == "platform"]
        if plats:
            ppos = member_coord(plats[0])
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


def member_coord(x):
    """Return (lat, lon) coordinates from a resolved relation member.
    Could be improved by calculating center of mass from ways etc."""
    if type(x) == overpy.Way:
        x.get_nodes(resolve_missing=True)
        lats = [ float(v.lat) for v in x.nodes ]
        lons = [ float(v.lon) for v in x.nodes ]
        lat = sum(lats) / len(x.nodes)
        lon = sum(lons) / len(x.nodes)
    elif type(x) == overpy.Relation:
        m = x.members[0].resolve(resolve_missing=True)
        (lat, lon) = member_coord(m)
    else:
        lat = float(x.lat)
        lon = float(x.lon)
    return (lat, lon)


def route_platforms(rel):
    retval = []
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
    for x in platforms:
        (lat, lon) = member_coord(x)
        ref = x.tags.get('ref', '<no ref in OSM>')
        name = x.tags.get('name', '<no name in OSM>')
        retval.append([float(lat),float(lon),ref,name])
    return retval


def route_stops(rel):
    retval = []
    stops = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "stop"]
    for x in stops:
        (lat, lon) = member_coord(x)
        name = x.tags.get('ref', '<no ref>')
        desc = x.tags.get('name', '<no name>')
        retval.append([float(lat),float(lon),name,desc])
    return retval


def stops_by_refs(refs, mode="bus"):
    """Return a list of OSM node ids which have one of the 'ref' tag values in
    a given refs list."""
    stoptags = mode2ovpstoptags(mode)
    refpat = "|".join(str(r) for r in refs)
    q = area + "(\n"
    for st in stoptags:
        q += 'node(area.hel){}[ref~"({})"];\n'.format(st, refpat)
        q += 'way(area.hel){}[ref~"({})"];\n'.format(st, refpat)
        q += 'rel(area.hel){}[ref~"({})"];\n'.format(st, refpat)
    q += "); out tags;"
    log.debug(q)
    rr = api.query(q)
    stopids = []
    for ref in refs:
        stopids.extend(("node", e.id) for e in rr.nodes if e.tags["ref"] == ref)
        stopids.extend(("way", e.id) for e in rr.ways if e.tags["ref"] == ref)
        stopids.extend(("relation", e.id) for e in rr.relations if e.tags["ref"] == ref)
    return stopids


def stops(mode="bus"):
    """Return all stops for a given mode in the area. The mode can also be
    a list of mode strings, in which case stops for all the modes listed
    are returned.

    A dict with ref as a key and tags dictionaries as values is returned.
    The following additional keys are included in the tag dictionaries:
    x:id    id of the object
    x:type  type if the object as a string of length 1 ('n', 'w', or 'r')
    x:latlon (latitude, longitude) tuple of the object, as calculated
            by osm.member_coord()
"""
    qtempl = "node(area.hel){};\nway(area.hel){};\nrel(area.hel){};"
    if isinstance(mode, list):
        qlist = [ e for m in mode for e in mode2ovpstoptags(m) ]
    else:
        qlist = mode2ovpstoptags(mode)
    q = "[out:json][timeout:120];\n" + area + "\n(\n" \
      + "\n".join([ qtempl.format(t, t, t) for t in qlist ]) + "\n);out body;"
    log.debug(q)
    rr = api.query(q)
    return sanitize_rr(rr)


def sanitize_rr(rr):
    def sanitize_add(sd, rd, elist, etype):
        for e in elist:
            dd =  { \
                "x:id": e.id,
                "x:type": etype,
                "x:latlon": member_coord(e),
            }
            dd.update(e.tags)
            ref = e.tags.get("ref", None)
            if ref:
                # sd is defaultdict(list)
                sd[ref].append(dd)
            else:
                # rd is dict
                rd[e.id] = dd
    refstops = defaultdict(list)
    rest = {}
    # NB: Because sanitize_add() calls member_coords(), which gets more
    # (untagged) nodes (and maybe ways), the order of calls below
    # must be like this.
    sanitize_add(refstops, rest, rr.nodes, "n")
    sanitize_add(refstops, rest, rr.ways, "w")
    sanitize_add(refstops, rest, rr.relations, "r")
    return refstops, rest


def rels_v2(lineref, mode="bus"):
    """Get public transport v2 lines corresponding to lineref in Helsinki area.
    """
    q = '%s\nrel(area.hel)[route="%s"][ref="%s"]["public_transport:version"="2"];(._;>;>;);out body;' % (area, mode, lineref)
    log.debug(q)
    rr = api.query(q)
    return rr.relations


def rels(lineref, mode="bus"):
    """Get all lines corresponding to lineref and mode in area.
    """
    q = '%s\nrel(area.hel)[route="%s"][ref="%s"];(._;>;>;);out body;' % (area, mode, lineref)
    log.debug(q)
    rr = api.query(q)
    return rr.relations

