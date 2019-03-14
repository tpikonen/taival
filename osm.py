import overpy
from collections import defaultdict
from util import ldist2

api = overpy.Overpass()
api.retry_timeout=120
api.max_retry_count=10
# Approximate HSL area = Helsinki + Porvoo regions
area = """(area[admin_level=7]["name"="Helsingin seutukunta"]["ref"="011"][boundary=administrative]; area[admin_level=7]["name"="Porvoon seutukunta"]["ref"="201"][boundary=administrative];)->.hel;"""


def relid2url(relid):
    return "https://www.openstreetmap.org/relation/" + str(relid)


def all_linerefs(mode="bus"):
    """Return a lineref:[urllist] dict of all linerefs in Helsinki region.
    URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[type=route][route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
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
    q = '%s rel(area.hel)[route="%s"][network~"HSL|Helsinki|Espoo|Vantaa"]["public_transport:version"="2"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = {r.tags["ref"]:relid2url(r.id)
            for r in rr.relations if "ref" in r.tags.keys()}
    return refs


def was_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all was:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[type="was:route"]["was:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs


def disused_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all disused:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '%s rel(area.hel)[type="disused:route"]["disused:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    rr = api.query(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs


def route_master(route_ids):
    """Get route master relation from Overpass"""
    q = '[out:json][timeout:60];(%s);(rel(br)["type"="route_master"];);out body;' \
      % ("".join(["rel(%d);" % x for x in route_ids]))
    rr = api.query(q)
    return rr.relations


def ndist2(n1, n2):
    """Return distance metric squared for two nodes n1 and n2."""
    return (n1.lat - n2.lat)**2 + (n1.lon - n2.lon)**2


def shape(rel):
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
        lat = x.nodes[0].lat
        lon = x.nodes[0].lon
    elif type(x) == overpy.Relation:
        m = x.members[0].resolve(resolve_missing=True)
        (lat, lon) = member_coord(m)
    else:
        lat = float(x.lat)
        lon = float(x.lon)
    return (lat, lon)


def platforms(rel):
    retval = []
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
    for x in platforms:
        (lat, lon) = member_coord(x)
        ref = x.tags.get('ref', '<no ref in OSM>')
        name = x.tags.get('name', '<no name in OSM>')
        retval.append([float(lat),float(lon),ref,name])
    return retval


def stops(rel):
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


def rel(relno):
    rr = api.query("rel(id:%d);(._;>;>;);out body;" % (relno))
    return rr.relations[0]


def rels_v2(lineref, mode="bus"):
    """Get public transport v2 lines corresponding to lineref in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"]["public_transport:version"="2"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr.relations


def rels(lineref, mode="bus"):
    """Get all lines corresponding to lineref and mode in Helsinki area.
    """
    q = '%s rel(area.hel)[route="%s"][ref="%s"];(._;>;>;);out body;' % (area, mode, lineref)
    rr = api.query(q)
    return rr.relations

