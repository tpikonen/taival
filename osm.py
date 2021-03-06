# Copyright (C) 2018-2021 Teemu Ikonen <tpikonen@gmail.com>

# This file is part of Taival.
# Taival is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License version 3 as published by the
# Free Software Foundation. See the file COPYING for license text.

import overpy, logging, time
from collections import defaultdict
from util import ldist2

log = logging.getLogger(__name__)

api = overpy.Overpass()
api.retry_timeout=30
api.max_retry_count=10

def apiquery(query):
    waittimes = [2,3,4,8] # min
    for t in waittimes:
        try:
            rr = api.query(query)
            return rr
        except overpy.exception.OverpassTooManyRequests:
            tsec = t * 60
            log.info(f"Too many Overpass requests, waiting {tsec} seconds.")
            time.sleep(tsec)
    log.error("Giving up on Overpass requests")
    raise overpy.exception.OverpassTooManyRequests("Giving up")

# Areas must be initialized by e.g. hsl.overpass_area before queries
area = None
stopref_area = None

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

stationtags = {
    "bus": [ { "amenity": "bus_station" } ],
    # "station": None means [!station] in overpass (i.e. no station tag)
    "train": [ { "railway": "station", "station": None } ],
    "subway": [ { "railway": "station", "station": "subway" } ],
    "light_rail": [ { "railway": "station", "station": "light_rail" } ],
}

citybiketags = [ { "amenity": "bicycle_rental" } ]

bikeparktags = [ { "amenity": "bicycle_parking" } ]

xtype2osm = {\
    'n': "node",
    'w': "way",
    'r': "relation",
}

# Helper functions

def relid2url(relid):
    return "https://www.openstreetmap.org/relation/" + str(relid)


def obj2url(s):
    return "https://www.openstreetmap.org/{}/{}".format(xtype2osm[s["x:type"]], s["x:id"])


def stoplist2links(stoplist):
    return " ".join("[{} {}]".format(obj2url(s), s["ref"]) for s in stoplist)


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


def ndist2(n1, n2):
    """Return distance metric squared for two nodes n1 and n2."""
    return (n1.lat - n2.lat)**2 + (n1.lon - n2.lon)**2

# route relations

overpy_route_cache = { k: None for k in list(stoptags.keys()) + ["minibus"] }

def get_route_rr(mode="bus"):
    """
    Return a (possibly cached) overpy.Result object with all the routes
    for mode in area.
    """
    if overpy_route_cache.get(mode, None):
        return overpy_route_cache[mode]
    q = '[out:json][timeout:600];%s\nrel(area.hel)[type=route][route="%s"][ref];(._;>;>;);out body;' % (area, mode)
    log.debug(q)
    rr = apiquery(q)
    overpy_route_cache[mode] = rr
    return rr


def all_linerefs(mode, networks):
    """
    Return a lineref:[urllist] dict of all linerefs which have
    "network" tag one of the values in networks list, or no network.
    URLs points to the relations in OSM.
    """
    rr = get_route_rr(mode)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys() and \
          (not "network" in r.tags.keys() or r.tags["network"] in networks):
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs


def rels_query(lineref, mode="bus"):
    """Get public transport routes corresponding to lineref in area from
    a direct query.
    """
    q = '%s\nrel(area.hel)[route="%s"][ref="%s"];(._;>;>;);out body;' % (area, mode, lineref)
    log.debug(q)
    rr = apiquery(q)
    return rr.relations


def rels_refless(mode):
    """
    Get routes for mode which do not have a ref tag.
    """
    q = '[out:json][timeout:300];%s\nrel(area.hel)[type=route][route="%s"][!ref];(._;);out tags;' % (area, mode)
    log.debug(q)
    rr = apiquery(q)
    return rr.relations


def rels(lineref, mode="bus", networks=None):
    """
    Get all lines corresponding to lineref and mode in area.
    """
    rr = get_route_rr(mode)
    retval = [ r for r in rr.relations if r.tags.get("ref", None) == lineref ]
    if networks:
        retval = [ r for r in retval if r.tags.get("network", None) in networks ]
    return retval


def rel_members_w_role(rel, rstart):
    """
    Return members of relation which have role starting with string rstart.
    The return value is a tuple (lat, lon, ref, name, role).
    """
    retval = []
    elems = [(mem.resolve(resolve_missing=True), mem.role) \
      for mem in rel.members if mem.role and mem.role.startswith(rstart)]
    for x, role in elems:
        (lat, lon) = member_coord(x)
        ref = x.tags.get('ref', '<no ref in OSM>')
        name = x.tags.get('name', '<no name in OSM>')
        retval.append((float(lat), float(lon), ref, name, role))
    return retval


def route_platforms(rel):
    """
    Return members of route relations with role 'platform*'.
    The return value is a tuple (lat, lon, ref, name, role).
    """
    return rel_members_w_role(rel, 'platform')


def route_stops(rel):
    """
    Return members of route relations with role 'stop*'.
    The return value is a tuple (lat, lon, ref, name, role).
    """
    return rel_members_w_role(rel, 'stop')


def route_platforms_or_stops(rel):
    """
    Return platforms for a route relation. If there are no relation
    members with a role 'platform*', return members with role 'stop*'
    instead.
    The return value is a tuple (lat, lon, ref, name, role).
    """
    if any(m.role.startswith('platform') for m in rel.members if m.role):
        return route_platforms(rel)
    else:
        return route_stops(rel)


def route_shape(rel):
    """Get route shape from overpy relation. Return a ([[lat,lon]], gaps)
    tuple, where gaps is True if the ways in route do not share endpoint
    nodes. """
    ways = [mem.resolve() for mem in rel.members
        if isinstance(mem, overpy.RelationWay) and (not mem.role or mem.role in ('forward', 'backward'))]
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
    gap_after_first = False
    if (ways[0].nodes[-1] == ways[1].nodes[0]) \
      or (ways[0].nodes[-1] == ways[1].nodes[-1]):
        nodes = ways[0].nodes
    elif (ways[0].nodes[0] == ways[1].nodes[0]) \
      or (ways[0].nodes[0] == ways[1].nodes[-1]):
        nodes = ways[0].nodes[::-1] # reverse
    elif ways[1].nodes[0] == ways[1].nodes[-1]:
        if not ways[1].tags.get("junction", None) == "roundabout":
            log.debug(f"Circular (2nd) way is not a roundabout in relation {rel.id} !")
        if ways[0].nodes[-1] in ways[1].nodes:
            nodes = ways[0].nodes
        elif ways[0].nodes[0] in ways[1].nodes:
            nodes = ways[0].nodes[::-1]
        else:
            gap_after_first = True
    else:
        gap_after_first = True
    if gap_after_first: # Orient first segment in case of a gap
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
    # flip ways when needed, split roundabout ways
    # Iterate with index, because we need to peek ways[i+1] for roundabouts
    for i in range(1, len(ways)):
        w = ways[i]
        if w.nodes[0] == w.nodes[-1]:
            if not w.tags.get("junction", None) == "roundabout":
                log.debug(f"Circular way is not a roundabout in relation {rel.id} !")
            startind = w.nodes.index(nodes[-1]) if nodes[-1] in w.nodes else None
            wnext = ways[i+1] if (i+1) < len(ways) else None
            if wnext:
                # This does not work with 2 roundabouts in a row
                if wnext.nodes[0] in w.nodes:
                    nextstart = wnext.nodes[0]
                elif wnext.nodes[-1] in w.nodes:
                    nextstart = wnext.nodes[-1]
                else:
                    nextstart = None
                nextind = w.nodes.index(nextstart) if nextstart else None
                # We don't add a duplicate startind node, but do add the
                # nextind node to the end of the node list in assignments
                # below, hence the +1's in slices
                if (not startind is None) and (not nextind is None):
                    if startind < nextind:
                        nodes.extend(w.nodes[(startind+1):(nextind+1)])
                    else:
                        nodes.extend(w.nodes[(startind+1):])
                        nodes.extend(w.nodes[:(nextind+1)])
                elif not startind is None:
                    gaps = True
                    nodes.extend(w.nodes[(startind+1):])
                    nodes.extend(w.nodes[:(startind+1)]) # include startind again
                elif not nextind is None:
                    gaps = True
                    nodes.extend(w.nodes[(nextind+1):])
                    nodes.extend(w.nodes[:(nextind+1)])
            else: # w is last way
                if not startind is None:
                    nodes.extend(w.nodes[(startind+1):])
                    nodes.extend(w.nodes[:(startind+1)])
                else:
                    gaps = True
                    nodes.extend(w.nodes)
        elif nodes[-1] == w.nodes[0]:
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

# Former routes

def was_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all was:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '[out:json][timeout:300];%s\nrel(area.hel)[type="was:route"]["was:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    log.debug(q)
    rr = apiquery(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs


def disused_routes(mode="bus"):
    """Return a lineref:[urllist] dict of all disused:route=<mode> routes in
    Helsinki region. URLs points to the relations in OSM."""
    q = '[out:json][timeout:300];%s\nrel(area.hel)[type="disused:route"]["disused:route"="%s"][network~"HSL|Helsinki|Espoo|Vantaa"];out tags;' % (area, mode)
    log.debug(q)
    rr = apiquery(q)
    refs = defaultdict(list)
    for r in rr.relations:
        if "ref" in r.tags.keys():
            refs[r.tags["ref"]].append(relid2url(r.id))
    return refs

# route_master relations

# ref -> route_master relation dict
overpy_route_master_dict = { k: None for k in list(stoptags.keys()) + ["minibus"] }

def get_route_master_dict(mode, agency):
    """
    Return a (possibly cached) ref->route_master rel dict with all
    route_master relations for mode and network (i.e. agency) with a ref.
    """
    if overpy_route_master_dict.get(mode, None):
        return overpy_route_master_dict[mode]
    q = '[out:json][timeout:300];rel[type=route_master][route_master="%s"][network="%s"];(._;>;>;);out body;' % (mode, agency)
    log.debug(q)
    rr = apiquery(q)
    rmd = defaultdict(list)
    for rel in rr.relations:
        ref = rel.tags.get("ref", None)
        if ref:
            rmd[ref].append(rel)
    overpy_route_master_dict[mode] = rmd
    return rmd


def route_master(route_ids):
    """Get route master relation from Overpass"""
    if not route_ids:
        log.error("route_master(): Empty route_ids list given")
        return []
    q = '[out:json][timeout:60];rel(id:%s);(rel(br)["type"="route_master"];);out body;' \
      % (",".join(str(x) for x in route_ids))
    log.debug(q)
    rr = apiquery(q)
    return rr.relations


# Stops

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


def mode2ovptags(mode, modetags=stoptags):
    """Return a list of Overpass tag filters."""
    tlist = modetags[mode]
    out = []
    for tags in tlist:
        ovp = ""
        for k, v in tags.items():
            if v:
                ovp += '["{}"="{}"]'.format(k, v)
            else:
                ovp += '[!"{}"]'.format(k)
        if ovp:
            out.append(ovp)
    return out


def stops_by_refs(refs, mode="bus"):
    """Return a list of OSM node ids which have one of the 'ref' tag values in
    a given refs list."""
    stoptags = mode2ovptags(mode)
    refpat = "|".join(str(r) for r in refs)
    q = stopref_area + "(\n"
    for st in stoptags:
        q += 'node(area.hel){}[ref~"({})"];\n'.format(st, refpat)
        q += 'way(area.hel){}[ref~"({})"];\n'.format(st, refpat)
        q += 'rel(area.hel){}[ref~"({})"];\n'.format(st, refpat)
    q += "); out tags;"
    log.debug(q)
    rr = apiquery(q)
    stopids = []
    for ref in refs:
        ids = []
        ids.extend(("node", e.id) for e in rr.nodes if e.tags["ref"] == ref)
        ids.extend(("way", e.id) for e in rr.ways if e.tags["ref"] == ref)
        ids.extend(("relation", e.id) for e in rr.relations if e.tags["ref"] == ref)
        if not ids:
            log.warning(f"OSM stop object not found for ref '{ref}'")
        elif len(ids) > 1:
            log.warning(f"More than OSM object for ref '{ref}': {', '.join(str(i) for i in ids)}")
        stopids.extend(ids)
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
        qlist = [ e for m in mode for e in mode2ovptags(m) ]
    else:
        qlist = mode2ovptags(mode)
    q = "[out:json][timeout:120];\n" + area + "\n(\n" \
      + "\n".join([ qtempl.format(t, t, t) for t in qlist ]) + "\n);out body;"
    log.debug(q)
    rr = apiquery(q)
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


def stations(mode="bus"):
    """Return all stations for a given mode in the area. The mode can also be
    a list of mode strings, in which case stations for all the modes listed
    are returned.

    A list with tags dictionaries as values is returned.
    The following additional keys are included in the tag dictionaries:
    x:id    id of the object
    x:type  type if the object as a string of length 1 ('n', 'w', or 'r')
    x:latlon (latitude, longitude) tuple of the object, as calculated
            by osm.member_coord()
"""
    qtempl = "node(area.hel){};\nway(area.hel){};\nrel(area.hel){};"
    if isinstance(mode, list):
        qlist = [ e for m in mode for e in mode2ovptags(m, stationtags) ]
    else:
        qlist = mode2ovptags(mode, stationtags)
    q = "[out:json][timeout:120];\n" + area + "\n(\n" \
      + "\n".join([ qtempl.format(t, t, t) for t in qlist ]) + "\n);out body;"
    log.debug(q)
    rr = apiquery(q)
    def sanitize_addlist(sl, elist, etype):
        for e in elist:
            dd =  { \
                "x:id": e.id,
                "x:type": etype,
                "x:latlon": member_coord(e),
            }
            dd.update(e.tags)
            sl.append(dd)
    stations = []
    # NB: Because sanitize_add() calls member_coords(), which gets more
    # (untagged) nodes (and maybe ways), the order of calls below
    # must be like this.
    sanitize_addlist(stations, rr.nodes, "n")
    sanitize_addlist(stations, rr.ways, "w")
    sanitize_addlist(stations, rr.relations, "r")
    return stations


def citybikes():
    """Return citybike stations."""
    qtempl = "node(area.hel){};\nway(area.hel){};\nrel(area.hel){};"
    qlist = []
    for tags in citybiketags:
        qlist.append(''.join([ '["{}"="{}"]'.format(k, v) for k, v in tags.items() ]))
    q = "[out:json][timeout:120];\n" + area + "\n(\n" \
      + "\n".join([ qtempl.format(t, t, t) for t in qlist ]) + "\n);out body;"
    log.debug(q)
    rr = apiquery(q)
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

