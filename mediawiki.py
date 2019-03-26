import difflib, sys
import osm, hsl
from util import *
from digitransit import pattern2url

outfile = None

style_problem = "background-color: #ffaaaa"
style_ok = "background-color: #aaffaa"
style_maybe = "background-color: #eeee00"
style_relstart = "border-style: solid; border-width: 1px 1px 1px 3px"
style_details = "background-color: #ffffff"

xtype2osm = {\
    'n': "node",
    'w': "way",
    'r': "relation",
}

def wr(*args, **kwargs):
    kwargs["file"] = outfile
    print(*args, **kwargs)


def wr_if(s, **kwargs):
    """Write s if it's not empty."""
    if s:
        wr(s, **kwargs)

def test_tag(ts, key, value=None, badtag=False):
    """Test if a tag has a given value or just exists, if value=None.
    Return a string describing a problem, or empty string if no problems."""
    if not key in ts.keys():
        out = "Tag '''%s''' not set" % key
        if badtag:
            out = ""
        elif value is not None:
            out += " (should be '%s')." % value
        else:
            out += "."
        return out
    else:
        tval = ts[key]
        if badtag:
            out = "Probably '''mispelled''' tag '''%s''' with value '%s'." \
              % (key, tval)
        elif value is None:
            out = ""
        elif tval != value:
            out = "Tag '''%s''' has value '%s' (should be '%s')." \
              % (key, tval, value)
        else:
            out = ""
        return out


def test_hsl_routename(ts, lineref, longname):
    """Do a special test for the route name-tag.
    Return an empty string if ok, a string describing the problem if not."""
    # Reittiopas longName field sometimes has dangling hyphens, remove them.
    longname = longname[1:] if longname[0] == '-' else longname
    longname = longname[:-1] if longname[-1] == '-' else longname
    stops = hsl.longname2stops(longname)
    name1 = lineref + " " + "–".join(stops) # Use en dash as a separator
    stops.reverse()
    name2 = lineref + " " + "–".join(stops)
    tag = ts.get("name", "")
    out = ""
    if tag == "":
        out = "Tag '''name''' not set (should be either '%s' or '%s')." \
          % (name1, name2)
    elif tag != name1 and tag != name2:
        out = "Tag '''name''' has value '%s' (should be either '%s' or '%s')." \
          % (tag, name1, name2)
    return out


def test_stop_positions(rel, mode="bus"):
    wr("'''Stop positions:'''\n")
    stops = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "stop"]
    platforms = [mem.resolve(resolve_missing=True) \
      for mem in rel.members if mem.role == "platform"]
#    wr("Route [%s %s] '%s' " % (osm.relid2url(rel.id), rel.id, \
#      rel.tags.get("name", "<no-name-tag>")))
    wr("%d stop_positions vs. %d platforms." \
      % (len(stops), len(platforms)))
    wr("")
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
#            wr(sout)
    wr("")


def test_stop_locations():
    # start to complain if stop pos is farther than this from HSL platform
    # FIXME: Turn the comparison around and complain about HSL platforms
    # missing stop positions?
    tol = 0.050 # km FIXME: needs to be bigger for mode=subway?
    osmstops = [osm.route_stops(rel) for rel in rels]
    for r in range(len(osmstops)):
        wr("Route '%s'." % (rels[r].tags.get("name", "<no-name-tag>")))
        wr("Stops: %d in OSM vs. %d in HSL.\n" \
        % (len(osmstops[r]), len(hslplatforms[r])))
        for i in range(len(osmstops[r])):
            pdists = [haversine(osmstops[r][i][:2], hslplatforms[r][x][:2])
                for x in range(len(hslplatforms[r])) ]
            pind = pdists.index(min(pdists))
            mind = pdists[pind]
            if mind > tol:
                wr(" Distance from OSM stop %s to HSL platform %s (%s)" %
                  (osmstops[r][i][2], hslplatforms[r][pind][2], \
                  hslplatforms[r][pind][3], mind*1000, tol*1000))


def print_route_master(ld):
    """Test if a route_master relation for lineref exists and contains the
    given route_ids."""
    lineref = ld["lineref"]
    mode = ld["mode"]
    rm_rels = ld["rm_rels"]
    route_ids = [r.id for r in ld["rels"]]

    nr = len(rm_rels)
    wr("'''Route master:'''")
    if nr < 1:
        wr("No route_master relation found.\n")
        return
    elif nr > 1:
        wr("More than one route_master relations found: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r.id), r.id) for r in rm_rels)))
        return
    elif nr == 1:
        rel = rm_rels[0]
        wr("Relation: [%s %s]\n" % (osm.relid2url(rel.id), rel.id))
    memrefs = [m.ref for m in rel.members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        wr("route_master has extra members: %s\n" % (", ".join("[%s %s]" \
          % (osm.relid2url(r), r) for r in refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        wr("Found matching routes not in route_master: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r), r) for r in routes_not_in_refs)))
    tags = rel.tags
    wr_if(test_tag(tags, "route_master", mode), end='\n\n')
    wr_if(test_tag(tags, "ref", lineref), end='\n\n')
    wr_if(test_tag(tags, "name"), end='\n\n')
    wr_if(test_tag(tags, "network", "HSL"), end='\n\n')

    wr("")


# FIXME: Use templates for output
def print_linedict(ld, agency):
    """Print a info from a line dict from collect_line()"""
    lineref = ld["lineref"]
    mode = ld["mode"]
    modecolors = agency["modecolors"]
    wr("== %s ==" % lineref)
    rels = ld["rels"]
    if(len(rels) < 1):
        wr("No route relations found in OSM.")
        return
    relids = [r.id for r in rels]

    print_route_master(ld)

    alsoids = ld["alsoids"]
    if alsoids:
        wr("Extra routes in OSM with the same ref: %s\n\n" % \
          (", ".join("[%s %d]" % (osm.relid2url(r), r) for r in alsoids)))
    if len(rels) > 2:
        wr("More than 2 matching OSM routes found: %s.\n" % \
          (", ".join("[%s %d]" \
            % (osm.relid2url(rid), rid) for rid in relids)))
        wr("Giving up.\n")
        return
    codes = ld["codes"]
    osm2hsl = ld["osm2hsl"]
    hsl2osm = ld["hsl2osm"]
    if len(codes) != 2:
        wr("%d route pattern(s) in HSL data, matching may be wrong.\n" \
          % (len(codes)))
        for i in range(len(relids)):
            wr(" %s -> %s" % \
              (relids[i], "None" if osm2hsl[i] is None else codes[osm2hsl[i]]))
        for i in range(len(codes)):
            wr(" %s -> %s" % \
              (codes[i], "None" if hsl2osm[i] is None else relids[hsl2osm[i]]))
    wr("")

    id2hslindex = ld["id2hslindex"]
    htags = ld["htags"]
    interval_tags = ld["interval_tags"]
    hslshapes = ld["hslshapes"]
    for rel in rels:
        wr("'''Route [%s %s] %s'''\n" \
          % (osm.relid2url(rel.id), rel.id, rel.tags.get("name", "")))
        hsli = id2hslindex[rel.id]

        wr("'''Tags:'''\n")
        # name-tag gets a special treatment
        wr_if(test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"]), end='\n\n')
        # FIXME: network != agency always
        wr_if(test_tag(rel.tags, "network", agency["name"]), end='\n\n')
        wr_if(test_tag(rel.tags, "from"), end='\n\n')
        wr_if(test_tag(rel.tags, "to"), end='\n\n')
        if modecolors[mode]:
            wr_if(test_tag(rel.tags, "colour", modecolors[mode]), end='\n\n')
        wr_if(test_tag(rel.tags, "color", badtag=True), end='\n\n')
        if hsli is not None and interval_tags:
            itags = ld["hslitags"][hsli]
            for k in sorted(itags.keys()):
                wr_if(test_tag(rel.tags, k, itags[k]), end='\n\n')

        if rel.tags.get("public_transport:version", "0") != "2":
            wr("Tag public_transport:version=2 not set in OSM route %s. Giving up." % (rel.id))
            continue

        if any(mem.role == 'forward' or mem.role == 'backward'
          for mem in rel.members):
            wr("OSM route(s) tagged with public_transport:version=2,")
            wr("but have members with 'forward' or 'backward' roles.")
            wr("Skipping shape, platform and stop tests.\n")
            continue

        wr("'''Shape:'''\n")
        if hsli is not None:
            tol = 30
            (shape, gaps) = osm.route_shape(rel)
            if gaps:
                wr("Route has '''gaps'''!\n")
            ovl = test_shape_overlap(shape, hslshapes[hsli], tol=tol)
            wr("Route [%s %s] overlap (tolerance %d m) with HSL pattern [%s %s] is '''%1.0f %%'''.\n" \
              % (osm.relid2url(rel.id), rel.id, tol, pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
        else:
            wr("Route %s overlap could not be calculated.\n" \
              % (rel.id))

        test_stop_positions(rel)

        hsli = id2hslindex[rel.id]
        # Platforms
        wr("'''Platforms:'''\n")
        hslplatforms = ld["hslplatforms"]
        if hsli is not None:
            osmplatform = osm.route_platforms(rel)
            hslplatform = hslplatforms[hsli]
            # FIXME: Add stop names to unified diffs after diffing, somehow
            #osmp = [p[2]+" "+p[3]+"\n" for p in osmplatform]
            #hslp = [str(p[2])+" "+str(p[3])+"\n" for p in hslplatform]
            osmp = [p[2]+"\n" for p in osmplatform]
            hslp = [p[2]+"\n" for p in hslplatform]
            diff = list(difflib.unified_diff(osmp, hslp, "OSM", "HSL"))
            if diff:
                outfile.writelines(" " + d for d in diff)
            else:
                wr(" => Identical platform sequences.\n")
        else:
            wr("Platforms could not be compared.")
        wr("")

    wr("")


def print_abstract(md):
    mode = md["mode"]
    wr("This is a comparison of OSM public transit route data with [%s %s] %s transit data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n" % (md["agencyurl"], md["agency"], mode))
    if mode == "subway":
        wr("See also [http://osmz.ru/subways/finland.html osmz.ru subway validator].\n")


def print_summary(md):
    osmdict = md["osmdict"]
    hsldict = md["hsldict"]
    osmlines = set(osmdict)
    hsllines = set(hsldict)
    hsl_locallines = set(md["hsl_localbus"])
    wr("= Summary of %s transit in %s region. =" % (md["mode"], md["agency"]))
    wr("%d lines in OSM.\n" % len(osmlines))
    wr("%d lines in %s.\n" % (len(hsllines), md["agency"]))

    osmextra = osmlines.difference(hsllines)
    osmextra = list(osmextra.difference(hsl_locallines))
    osmextra.sort(key=linesortkey)
    wr("%d lines in OSM but not in HSL:" % len(osmextra))
    if osmextra:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in osmextra ] ))
    wr("")

    hslextra = list(hsllines.difference(osmlines))
    hslextra.sort(key=linesortkey)
    wr("%d lines in HSL but not in OSM:" % len(hslextra))
    if hslextra:
        wr(" %s" % ", ".join(["[%s %s]" % (hsldict[x], x) for x in hslextra]))
    wr("")

    commons = list(hsllines.intersection(osmlines))
    commons.sort(key=linesortkey)
    wr("%d lines in both HSL and OSM." % len(commons))
    if commons:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in commons] ))
    wr("")

def print_localbus(md):
    hsl_localbus = md["hsl_localbus"]
    hsl_locallines = set(hsl_localbus)
    osmdict = md["osmdict"]
    osmlines = set(osmdict)
    lbuses = list(hsl_locallines)
    lbuses.sort(key=linesortkey)
    wr("= Local bus lines =")
    wr("%d bus routes with GTFS type 704 (lähibussi) in %s." \
        % (len(lbuses), md["agency"]))
    if lbuses:
        wr(" %s" % ", ".join(["[%s %s]" % (hsl_localbus[x], x) \
          for x in lbuses] ))
    wr("")
    lcommons = list(hsl_locallines.intersection(osmlines))
    lcommons.sort(key=linesortkey)
    wr("%d normal bus routes in OSM with %s local bus route number." \
        % (len(lcommons), md["agency"]))
    if lcommons:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in lcommons ] ))
    wr("")
    osm_minibusdict = md["osm_minibusdict"]
    osm_minibuslines = list(osm_minibusdict)
    osm_minibuslines.sort(key=linesortkey)
    wr("%d route=minibus routes in OSM." % (len(osm_minibuslines)))
    if osm_minibuslines:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (osm_minibusdict[x][z], z+1) \
            for z in range(len(osm_minibusdict[x]))])) \
            for x in osm_minibuslines ] ))
    wr("")


def print_oldlines(md):
    mode = md["mode"]
    wasroutes = md["wasroutes"]
    wr("= Old lines =")
    waslines = list(wasroutes)
    waslines.sort(key=linesortkey)
    wr("%d routes with type 'was:route=%s'." % (len(wasroutes), mode))
    if wasroutes:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (wasroutes[x][z], z+1) \
            for z in range(len(wasroutes[x]))])) for x in waslines] ))
    wr("")

    disroutes = md["disroutes"]
    dislines = list(disroutes)
    dislines.sort(key=linesortkey)
    wr("%d routes with type 'disused:route=%s'." % (len(disroutes), mode))
    if disroutes:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (disroutes[x][z], z+1) \
            for z in range(len(disroutes[x]))])) for x in dislines] ))
    wr("")


def print_modedict(md):
    """Print modedict"""
    mode = md["mode"]
    agency = md["agency"]
    agencyurl = md["agencyurl"]
    osmdict = md["osmdict"]
    hsldict = md["hsldict"]
    hsl_localbus = md["hsl_localbus"]
    osm2dict = md["osm2dict"]

    osmlines = set(osmdict)
    hsllines = set(hsldict)
    hsl_locallines = set(hsl_localbus)

    print_abstract(md)
    print_summary(md)

    osm2lines = set(osm2dict)
    commons2 = list(hsllines.intersection(osm2lines))
    commons2.sort(key=linesortkey)
    wr("%d lines in both HSL and OSM with public_transport:version=2 tagging.\n" % len(commons2))
    wr(" %s" % ", ".join("[[#%s|%s]]" % (s, s) for s in commons2))
    wr("")

    if mode == "bus":
        print_localbus(md)

    print_oldlines(md)

    lines = md["lines"]
    wr("= Lines =")
    agdict = { "name" : agency, "modecolors" : md["modecolors"] }
    for l in lines:
        print_linedict(lines[l], agdict)


def cell_route_master(ld):
    """Return a (style, cell, details) tuple, where style is the cell style
    and cell is contents of the 'Master' cell in line table, possible
    problems are reported in details string."""

    lineref = ld["lineref"]
    mode = ld["mode"]
    rm_rels = ld["rm_rels"]
    route_ids = [r.id for r in ld["rels"]]

    nr = len(rm_rels)
    if nr < 1:
        return "", "No", ""
    elif nr > 1:
        style = style_problem
        cell = "more than 1"
        details = "'''Route master'''\nMore than one route_master relations found: %s\n" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r.id), r.id) for r in rm_rels))
        return style, cell, details
    elif nr == 1:
        rel = rm_rels[0]
        cell = "[%s %s]" % (osm.relid2url(rel.id), rel.id)
    detlist= []
    memrefs = [m.ref for m in rel.members]
    refs_not_in_routes = [r for r in memrefs if r not in route_ids]
    if refs_not_in_routes:
        detlist.append("route_master has extra members: %s" % (", ".join("[%s %s]" \
          % (osm.relid2url(r), r) for r in refs_not_in_routes)))
    routes_not_in_refs = [r for r in route_ids if r not in memrefs]
    if routes_not_in_refs:
        detlist.append("Found matching routes not in route_master: %s" \
          % (", ".join("[%s %s]" \
            % (osm.relid2url(r), r) for r in routes_not_in_refs)))
    tags = rel.tags
    detlist.append(test_tag(tags, "route_master", mode))
    detlist.append(test_tag(tags, "ref", lineref))
    detlist.append(test_tag(tags, "name"))
    detlist.append(test_tag(tags, "network", "HSL"))
    if any(detlist): # prepend header
        style = style_problem
        cell = cell + "[[#{} | diffs]]".format(ld["lineref"])
        details = "'''Route master:'''\n\n" \
          + "\n\n".join(s for s in detlist if s) + "\n\n"
    else:
        style = style_ok
        details = ""
    return style, cell, details


def print_table(md):
    header = """{| class="wikitable"
|-
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: solid; border-width: 1px 1px 1px 3px" colspan=5 | Direction 0
! style="border-style: solid; border-width: 1px 1px 1px 3px" colspan=5 | Direction 1"""
    subheader = """|-
! Line
! Master
! Extra
! Match
! style="border-style: solid; border-width: 1px 1px 1px 3px" | OSM
! HSL
! Tags
! Shape
! Platf.
! style="border-style: solid; border-width: 1px 1px 1px 3px" | OSM
! HSL
! Tags
! Shape
! Platf."""
    footer = "|}"

    mode = md["mode"]
    wr("= PTv2 tagged {} lines in OSM =\n".format(md["agency"]))
    wr("This table compares {} routes with".format(mode))
    wr("[[Key:public_transport:version | public_transport:version=2]] tag set.")
    wr("The checker uses [[Proposed_features/Refined_Public_Transport | Refined public transport schema]]")
    wr("as a reference.")
    wr("")
    wr(header)
    linecounter = 0
    lines_w_probs = 0
    for line in md["lines"]:
        cells = []
        ld = md["lines"][line]
        ld["details"] = ""
        # Line, add a placeholder, edited later
        cells.append(("", ""))
        # Master
        rm_style, rm_cell, rm_details = cell_route_master(ld)
        if rm_details:
            ld["details"] += rm_details
        cells.append((rm_style, rm_cell))
        # Extra
        if ld["alsoids"]:
            ld["details"] += "Extra routes in OSM with the same ref: %s\n\n" % \
              (", ".join("[%s %d]" % (osm.relid2url(r), r) for r in ld["alsoids"]))
            cells.append((style_problem, "[[#{} | yes]]".format(line)))
        else:
            cells.append((style_ok, "No"))
        # Match
        relids = [r.id for r in ld["rels"]]
        codes = ld["codes"]
        osm2hsl = ld["osm2hsl"]
        hsl2osm = ld["hsl2osm"]
        if len(ld["rels"]) > 2:
            ld["details"] += "More than 2 matching OSM routes found: %s.\n" % \
              (", ".join("[%s %d]" % (osm.relid2url(rid), rid) for rid in relids))
            ld["details"] += "Giving up.\n"
            cells.append((style_problem, "[[#{} | no]]".format(line)))
            continue
        elif len(codes) != 2:
            ld["details"] += "%d route pattern(s) in %s data, matching may be wrong.\n" \
              % (len(codes), md["agency"])
            for i in range(len(relids)):
                ld["details"] += " %s -> %s\n" % \
                  (relids[i], "None" if osm2hsl[i] is None else codes[osm2hsl[i]])
            for i in range(len(codes)):
                ld["details"] += " %s -> %s\n" % \
                  (codes[i], "None" if hsl2osm[i] is None else relids[hsl2osm[i]])
            cells.append((style_maybe, "[[#{} | maybe]]".format(line)))
        else:
            cells.append((style_ok, "Uniq."))
        # Directions / OSM relations
        id2hslindex = ld["id2hslindex"]
        htags = ld["htags"]
        dirindex = 0
        for rel in ld["rels"]:
            dirdetails = ""
            # OSM
            cells.append((style_relstart, "[%s %s]" % (osm.relid2url(rel.id), rel.id)))
            # HSL
            hsli = id2hslindex[rel.id]
            cells.append(("", "[%s %s]" % (pattern2url(codes[hsli]),  codes[hsli])))
            # Tags
            tdetlist = []
            # name-tag gets a special treatment
            tdetlist.append(test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"]))
            # FIXME: network != agency always
            tdetlist.append(test_tag(rel.tags, "network", md["agency"]))
            tdetlist.append(test_tag(rel.tags, "from"))
            tdetlist.append(test_tag(rel.tags, "to"))
#            if md["modecolors"][mode]:
#                tdetlist.append(test_tag(rel.tags, "colour", md["modecolors"][mode]))
            tdetlist.append(test_tag(rel.tags, "color", badtag=True))
            if hsli is not None and md["interval_tags"]:
                itags = ld["hslitags"][hsli]
                for k in sorted(itags.keys()):
                    tdetlist.append(test_tag(rel.tags, k, itags[k]))

            if rel.tags.get("public_transport:version", "0") != "2":
                dirdetails += "Tag public_transport:version=2 not set. Tests below are probably not correct.\n\n"
                dirdetails += "'''Tags:\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                cells.append((style_problem, "[[#{} | no PTv2]]".format(line)))
            elif any(mem.role == 'forward' or mem.role == 'backward'
              for mem in rel.members):
                dirdetails += "OSM route tagged with public_transport:version=2,"
                dirdetails += "but has members with 'forward' or 'backward' roles."
                dirdetails += "Tests below are probably not correct.\n\n"
                dirdetails += "'''Tags:\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                cells.append((style_problem, "[[#{} | PTv1]]".format(line)))
            elif any(tdetlist):
                dirdetails += "'''Tags:'''\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                cells.append((style_problem, "[[#{} | diffs]]".format(line)))
            else:
                cells.append((style_ok, "OK"))
            # Shape
            sdetlist = []
            if hsli is not None:
                tol = 30
                (shape, gaps) = osm.route_shape(rel)
                ovl = test_shape_overlap(shape, ld["hslshapes"][hsli], tol=tol)
                if gaps:
                    sdetlist.append("Route has '''gaps'''!")
                    sdetlist.append("Route [%s %s] overlap (tolerance %d m) with %s pattern [%s %s] is '''%1.0f %%'''." \
                      % (osm.relid2url(rel.id), rel.id, tol, md["agency"], pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
                    cells.append((style_problem, "[[#{} | gaps]]".format(line)))
                elif ovl <= 0.90:
                    sdetlist.append("Route [%s %s] overlap (tolerance %d m) with %s pattern [%s %s] is '''%1.0f %%'''." \
                      % (osm.relid2url(rel.id), rel.id, tol, md["agency"], pattern2url(codes[hsli]),  codes[hsli], ovl*100.0))
                    cells.append((style_problem, "%1.0f%%" % (ovl*100.0)))
                elif ovl <= 0.95:
                    cells.append((style_maybe, "%1.0f%%" % (ovl*100.0)))
                else:
                    cells.append((style_ok, "%1.0f%%" % (ovl*100.0)))
            else:
                sdetlist.append("Route %s overlap could not be calculated.\n" \
                  % (rel.id))
                cells.append((style_problem, "[[#{} | error]]".format(line)))
            if any(sdetlist):
                dirdetails += "'''Shape:'''\n\n" + "\n\n".join(sdetlist) + "\n\n"
            # Platforms
            hsli = id2hslindex[rel.id]
            hslplatforms = ld["hslplatforms"]
            if hsli is not None:
                osmplatform = osm.route_platforms(rel)
                hslplatform = hslplatforms[hsli]
                # FIXME: Add stop names to unified diffs after diffing, somehow
                #osmp = [p[2]+" "+p[3]+"\n" for p in osmplatform]
                #hslp = [str(p[2])+" "+str(p[3])+"\n" for p in hslplatform]
                osmp = [p[2]+"\n" for p in osmplatform]
                hslp = [p[2]+"\n" for p in hslplatform]
                diff = list(difflib.unified_diff(osmp, hslp, "OSM", md["agency"]))
                if diff:
                    dirdetails += "'''Platforms:'''\n\n"
                    dirdetails += "{}/{} platforms in OSM / {}.\n".format(len(osmp), len(hslp), md["agency"])
                    dirdetails += " " + diff[0]
                    dirdetails += " " + diff[1]
                    ins = 0
                    rem = 0
                    for d in diff[2:]:
                        dirdetails += " " + d
                        if d[0] == '+':
                            ins += 1
                        elif d[0] == '-':
                            rem += 1
                    cells.append((style_problem, "[[#{} | +{} -{}]]"\
                      .format(line, ins, rem)))
                else:
                    cells.append((style_ok, "{}/{}".format(len(osmp), len(hslp))))
            else:
                dirdetails += "'''Platforms:'''\n\n"
                dirdetails += "Platforms could not be compared."
                cells.append((style_problem, "[[#{} | error]]".format(line)))
            # Add per direction details
            if dirdetails:
                ld["details"] += \
                  "'''Direction {}''', route [{} {}], [{} {}]\n\n"\
                    .format(dirindex, osm.relid2url(rel.id), rel.id,\
                      pattern2url(codes[hsli]),  codes[hsli]) + dirdetails
            dirindex += 1
            # end 'for rel in rels'
        if linecounter % 20 == 0:
            wr(subheader)
        linecounter += 1
        wr("|-")
        if any(c[0] == style_problem for c in cells):
            cells[0] = (style_problem, "[[#{} | {}]]".format(line, line))
            lines_w_probs += 1
        else:
            cells[0] = (style_ok, str(line))
        for style, content in cells:
            wr('| style="{}" | {}'.format(style, content))

    wr(footer)
    wr("")
    wr("{} lines total.\n".format(linecounter))
    wr("{} lines with differences.".format(lines_w_probs))

    # details
    if any(ld["details"] for ld in md["lines"].values()):
        wr("= Details on differences =\n")
    else:
        return
    for ld in md["lines"].values():
        if ld["details"]:
            wr("== {} ==".format(ld["lineref"]))
            wr(ld["details"])


def report_tabular(md):
    """Write a mediawiki report page with summary and line table."""
    print_abstract(md)
    print_summary(md)
    if md["mode"] == "bus":
        print_localbus(md)
    print_oldlines(md)
    print_table(md)


def check_type(os):
    type2style = {
        "node": style_ok,
        "way": style_maybe,
        "relation": style_problem,
    }
    osmtype = xtype2osm[os["x:type"]]
    text = "[https://www.openstreetmap.org/{}/{} {}]".format(osmtype, os["x:id"], osmtype)
    return type2style[osmtype], text


def check_dist(os, ps):
    """Return a (style, text) tuple for distance between OSM and provider stops."""
    op = os.get("x:latlon", None)
    pp = ps.get("latlon", None)
    if op and pp:
        dist = haversine(op, pp)
        if dist > 0.999:
            return style_problem, "{0:.1f} km".format(dist)
        elif dist > 0.050:
            return style_problem, "{0:.0f} m".format(dist*1000)
        else:
            return style_ok, "{0:.0f} m".format(dist*1000)
    else:
        return style_problem, "Error"

def check_name(os, ps):
    """Return (style, text, details) cell tuple comparing name value."""
    on = os.get("name", None)
    pn = hsl.get_stopname(ps)
    if on:
        if on == pn:
            return (style_ok, "OK", "")
        else:
            details = "'''name''' set to '{}', should be '{}'."\
              .format(on, pn)
            return (style_problem, "diffs", details)
    else:
        details = "'''name''' not set in OSM, should be '{}'."\
          .format(pn if pn else "<No name in HSL>")
        return (style_problem, "no", details)


def check_findr(os):
    """Return (style, text) tuple for presence of ref:findr tag in OSM."""
    # FIXME: does not compare the actual value against Digiroad data
    findr = os.get("ref:findr", None)
    if findr:
        return (style_ok, str(findr))
    else:
        return (style_problem, "no")


def check_zone(os, ps):
    """Return (style, text) cell tuple comparing zone:HSL value."""
    oz = os.get("zone:HSL", None)
    pzid = ps.get("zoneId", None)
    pz = hsl.zoneid2name[pzid] if pzid else "?"
    if oz:
        if oz == pz:
            return (style_ok, oz)
        else:
            return (style_problem, "{}/{}".format(oz, pz))
    else:
        if pz == 'no':
            return (style_ok, "no")
        else:
            return (style_problem, pz)


def check_wheelchair(os, ps):
    """Return (cell style, text) string tuple comparing wheelchair
    accessibility for a stop."""
    ow = os.get("wheelchair", None)
    pw = ps.get("wheelchairBoarding", None)
    if not ow:
        if not pw:
            return (style_problem, "?/err1")
        elif pw == "NO_INFORMATION":
            return (style_ok, "?/?")
        elif pw == "POSSIBLE":
            return (style_problem, "?/yes")
        elif pw == "NOT_POSSIBLE":
            return (style_problem, "?/no")
        else:
            return (style_problem, "?/err2")
    elif ow == 'yes' or ow == 'limited' or ow == 'designated':
        if not pw:
            return (style_problem, "yes/err1")
        elif pw == "NO_INFORMATION":
            return (style_maybe, "yes/?")
        elif pw == "POSSIBLE":
            return (style_ok, "yes/yes")
        elif pw == "NOT_POSSIBLE":
            return (style_problem, "yes/no")
        else:
            return (style_problem, "yes/err2")
    elif ow == 'no':
        if not pw:
            return (style_problem, "no/err1")
        elif pw == "NO_INFORMATION":
            return (style_maybe, "no/?")
        elif pw == "POSSIBLE":
            return (style_problem, "no/yes")
        elif pw == "NOT_POSSIBLE":
            return (style_ok, "no/no")
        else:
            return (style_problem, "no/err2")
    else:
        return (style_problem, "err")


def print_stoptable_cluster(sd, refs=None):
    cols = 9
    header = '{| class="wikitable"\n|-\n! colspan=%d | Cluster' % (cols)
    subheader = """|-
! ref
! HSL code
! mode
! type
! delta
! name
! ref:findr
! zone:HSL
! wheelch."""
    footer = "|}"

    ost = sd["ost"]
    pst = sd["pst"] # data from provider
    pcl = sd["pcl"]

    if refs:
        kk = refs
    else:
        kk = list(ost.keys())
    kk = [ k for k in kk if pst.get(k, None) ]
    kk.sort()
    wc = ost.copy() # working copy
    linecounter = 0
    wr(header)
    wr(subheader)
    for k in kk:
        if linecounter > 20:
            wr(subheader)
            linecounter = 0
        s = wc.get(k, None)
        if not s:
            continue
        c = pst[k]["cluster"]
        clist = list(set(pcl[c["gtfsId"]]))
        clist.sort()
        linecounter += len(clist) + 1
        wr("|-")
        wr("|colspan={} | {}".format(cols, c["name"]))
        for ref in clist:
            detlist = []
            wr("|-")
            os = wc.pop(ref, None)
            ps = pst[ref]
            wr("| {}".format(ref))
            wr("| [https://reittiopas.hsl.fi/pysakit/{} {}]"\
              .format(ps["gtfsId"], ps["gtfsId"]))
            # FIXME: Make ost dict to be ref -> taglist, complain if it has more than 1 item
            if os:
                wr("| {}".format(ps["mode"])) # FIXME: check mode tags from OSM
                wr('| style="{}" | {}'.format(*check_type(os)))
                wr('| style="{}" | {}'.format(*check_dist(os, ps)))
                (st, txt, details) = check_name(os, ps)
                if details:
                    detlist.append(details)
                wr('| style="{}" | {}'.format(st, txt))
                wr('| style="{}" | {}'.format(*check_findr(os)))
                wr('| style="{}" | {}'.format(*check_zone(os, ps)))
                wr('| style="{}" | {}'.format(*check_wheelchair(os, ps)))
                if detlist:
                    wr('|-')
                    wr('| colspan={} style="{}" | {}'.format(cols, style_details, "\n".join(detlist)))
            else:
                (lat, lon) = ps["latlon"]
                wr('| colspan={} style="{}" | missing from [https://www.openstreetmap.org/#map=19/{}/{} OSM]'.format(cols-3, style_problem, lat, lon))
                wr('|-')
                taglist = []
                taglist.append("'''name'''='{}'".format(hsl.get_stopname(ps)))
                pzid = ps.get("zoneId", None)
                if pzid and pzid != 99:
                    taglist.append("'''zone:HSL'''='{}'".format(hsl.zoneid2name[pzid]))
                pw = ps.get("wheelchairBoarding", None)
                if pw and pw == 'POSSIBLE':
                    taglist.append("'''wheelchair'''='yes'")
                elif pw and pw == 'NOT_POSSIBLE':
                    taglist.append("'''wheelchair'''='no'")
                desc = "Mode is {}. ".format(ps["mode"])
                desc += "Tags from HSL: " + ", ".join(taglist) + "."
                wr('| colspan={} style="{}" | {}'.format(cols, style_details, desc))

    wr(footer)
    wr("")


def report_stoptable_cluster(sd, city):
    prefixes = hsl.city2prefixes[city]
    pattern = re.compile("^(" + "|".join(prefixes) + ")[0-9]{4,4}$")
    pst = sd["pst"]
    refs = [ k for k in pst.keys() if pattern.match(k) ]
    print_stoptable_cluster(sd, refs)
