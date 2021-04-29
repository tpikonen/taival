import difflib, sys, logging
import osm, hsl
from util import *
from digitransit import pattern2url, terminalid2url, citybike2url

log = logging.getLogger(__name__)

outfile = None

style_problem = "background-color: #ffaaaa"
style_ok = "background-color: #aaffaa"
style_maybe = "background-color: #eeee00"
style_relstart = "border-style: solid; border-width: 1px 1px 1px 3px"
style_details = "background-color: #ffffff"

# Match codes with last number '0'
zerocodepat = re.compile("^..*0[^0-9]*$")

def wr(*args, **kwargs):
    kwargs["file"] = outfile
    print(*args, **kwargs)


def wr_if(s, **kwargs):
    """Write s if it's not empty."""
    if s:
        wr(s, **kwargs)


def keykey(dkey, return_type=str):
    return lambda x: x.get(dkey, return_type())


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
    tag = ts.get("name", "")
    # Reittiopas longName field sometimes has dangling hyphens, remove them.
    longname = longname[1:] if longname[0] == '-' else longname
    longname = longname[:-1] if longname[-1] == '-' else longname
    stops = hsl.longname2stops(longname)
    stopnames1 = "–".join(stops) # Use en dash as a separator
    name1 = f"{lineref} {stopnames1}"
    stops.reverse()
    stopnames2 = "–".join(stops) # Use en dash as a separator
    name2 = f"{lineref} {stopnames2}"
    # Handle ferry routes without ref number
    if lineref == longname:
        if tag == "":
            out = "Tag '''name''' not set (should be '%s')." \
              % (longname)
        # Also allow a name derived from stops for ferry routes
        elif tag == stopnames1 or tag == stopnames2:
            out = ""
        elif tag != longname:
            out = "Tag '''name''' has value '%s' (should be '%s')." \
              % (tag, longname)
        else:
            out = ""
        return out
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


def print_abstract(md):
    mode = md["mode"]
    wr("This is a comparison of OSM public transit route data with [%s %s] %s transit data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n" % (md["agencyurl"], md["agency"], mode))
    if mode == "subway":
        wr("See also [http://osmz.ru/subways/finland.html osmz.ru subway validator].\n")


def print_summary(md):
    osmdict = md["osmdict"]
    hsldict = md["hsldict"]
    refless = md["refless"]
    osmlines = set(osmdict)
    hsllines = set(hsldict)
    wr("= Summary of %s transit in %s region. =" % (md["mode"], md["agency"]))
    wr("%d lines in OSM.\n" % len(osmlines))
    wr("%d lines in %s.\n" % (len(hsllines), md["agency"]))

    osmextra = osmlines.difference(hsllines)
    if md["mode"] == "bus":
        hsl_locallines = set(md["hsl_localbus"])
        osmextra = list(osmextra.difference(hsl_locallines))
    else:
        osmextra = list(osmextra)
    osmextra.sort(key=linesortkey)
    wr("%d lines in OSM but not in %s:" % (len(osmextra), md["agency"]))
    if osmextra:
        wr(" %s" % ", ".join(["%s (%s)" % \
          (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
            for z in range(len(osmdict[x]))])) for x in osmextra ] ))
    wr("")

    hslextra = list(hsllines.difference(osmlines))
    hslextra.sort(key=linesortkey)
    wr("%d lines in %s but not in OSM:" % (len(hslextra), md["agency"]))
    if hslextra:
        wr(" %s" % ", ".join(["[%s %s]" % (hsldict[x], x) for x in hslextra]))
    wr("")

    wr(f"{len(refless)} lines without a 'ref' tag:")
    if refless:
        wr(" %s" % ", ".join(["[%s %s]" % (osm.relid2url(r.id), r.tags.get("name", str(r.id))) for r in refless]))
    wr("")

#    commons = list(hsllines.intersection(osmlines))
#    commons.sort(key=linesortkey)
#    wr("%d lines in both %s and OSM." % (len(commons), md["agency"]))
#    if commons:
#        wr(" %s" % ", ".join(["%s (%s)" % \
#          (x, ", ".join(["[%s %d]" % (osmdict[x][z], z+1) \
#            for z in range(len(osmdict[x]))])) for x in commons] ))
#    wr("")

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


def print_routetable(md, linerefs=None, networkname=None, platformidx=2):
    """
    Print a route table and details on differences from modedict for
    refs given in linerefs arg (by default all).

    If the name of the network differs from agency/provider name, it can
    be given in the networkname arg.

    The platformidx arg gives the index of the member in the platform
    tuple (lat, lon, ref, name) to be compared in the platform sequence
    diffs. The default is 2=ref, but some routes do not have platforms with
    refs, so 3=name can also be used).
    """
    header = """{| class="wikitable"
|-
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: none" |
! style="border-style: solid; border-width: 1px 1px 1px 3px" colspan=5 | Direction 0
! style="border-style: solid; border-width: 1px 1px 1px 3px" colspan=5 | Direction 1"""
    subheader = """|-
! Route
! Master
! Match
! style="border-style: solid; border-width: 1px 1px 1px 3px" | OSM
! {}
! Tags
! Shape
! Platf.
! style="border-style: solid; border-width: 1px 1px 1px 3px" | OSM
! {}
! Tags
! Shape
! Platf."""
    subheader = subheader.format(md["agency"], md["agency"])
    footer = "|}"

    def print_cells(cells, linecounter, statcounter, lines_w_probs):
        if (zerocodepat.match(line) and linecounter > 9) or linecounter > 30:
            wr(subheader)
            linecounter = 0
        linecounter += 1
        statcounter += 1
        wr("|-")
        if any(c[0] == style_problem for c in cells):
            cells[0] = (style_problem, "[[#{} | {}]]".format(line, line))
            lines_w_probs += 1
        else:
            cells[0] = (style_ok, str(line))
        for style, content in cells:
            wr('| style="{}" | {}'.format(style, content))
        return (linecounter, statcounter, lines_w_probs)

    mode = md["mode"]
    if not networkname:
        networkname = md["agency"]
    wr("= {} {} lines in OSM =\n".format(networkname, mode))
    wr("This table compares {} {} routes with OSM routes.".format(networkname, mode))
    wr("The checker uses [[Proposed_features/Refined_Public_Transport | Refined public transport schema]]")
    wr("as a reference.")
    wr("")
    wr(header)
    wr(subheader)
    linecounter = 0
    statcounter = 0
    lines_w_probs = 0

    if not linerefs:
        linerefs = [ e['lineref'] for e in md["lines"].values() ]

    for line in linerefs:
        cells = []
        ld = md["lines"][line]
        if not "rels" in ld.keys():
            continue
        ld["details"] = ""
        # Line, add a placeholder, edited later
        cells.append(("", ""))
        # Master
        rm_style, rm_cell, rm_details = cell_route_master(ld)
        if rm_details:
            ld["details"] += rm_details
        cells.append((rm_style, rm_cell))
        # Match
        relids = [r.id for r in ld["rels"]]
        codes = ld["codes"]
        osm2hsl = ld["osm2hsl"]
        hsl2osm = ld["hsl2osm"]
        if len(ld["rels"]) == len(codes) and all(x is not None for x in osm2hsl):
            cells.append((style_ok, "Uniq."))
        elif len(ld["rels"]) > 2:
            ld["details"] += "More than 2 matching OSM routes found: %s.\n" % \
              (", ".join("[%s %d]" % (osm.relid2url(rid), rid) for rid in relids))
            cells.append((style_problem, "[[#{} | no]]".format(line)))
            (linecounter, statcounter, lines_w_probs) = print_cells(cells, linecounter, statcounter, lines_w_probs)
            wr('| colspan=10 | Matching problem, see details')
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
            if hsli is not None:
                cells.append(("", "[%s %s]" % (pattern2url(codes[hsli]),  codes[hsli])))
            else:
                cells.append(("", "N/A"))
            # Tags
            tdetlist = []
            # name-tag gets a special treatment
            tdetlist.append(test_hsl_routename(rel.tags, htags["shortName"],  htags["longName"]))
            tdetlist.append(test_tag(rel.tags, "network", networkname))
            tdetlist.append(test_tag(rel.tags, "from"))
            tdetlist.append(test_tag(rel.tags, "to"))
#            if md["modecolors"][mode]:
#                tdetlist.append(test_tag(rel.tags, "colour", md["modecolors"][mode]))
            tdetlist.append(test_tag(rel.tags, "color", badtag=True))
            if hsli is not None and md["interval_tags"]:
                itags = ld["hslitags"][hsli]
                for k in sorted(itags.keys()):
                    tdetlist.append(test_tag(rel.tags, k, itags[k]))

            if any(tdetlist):
                dirdetails += "'''Tags:'''\n\n" + "\n\n".join([s for s in tdetlist if s]) + "\n\n"
                cells.append((style_problem, "[[#{} | diffs]]".format(line)))
            else:
                cells.append((style_ok, "OK"))
            ptv1 = any(mem.role in ('forward', 'backward') for mem in rel.members)
            # Shape
            sdetlist = []
            if hsli is not None:
                if ptv1:
                    sdetlist.append("Route [%s %s] has ways with 'forward' and 'backward' roles (PTv1)." \
                      % (osm.relid2url(rel.id), rel.id))
                    cells.append((style_problem, "PTv1"))
                elif len(ld["hslshapes"][hsli]) <= len(ld["hslplatforms"][hsli]):
                    cells.append((style_maybe, "N/A"))
                else:
                    tol = md["shapetol"]
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
                sdetlist.append(f"Shape for route {rel.id} not available from provider.\n")
                cells.append((style_problem, "[[#{} | N/A]]".format(line)))
            if any(sdetlist):
                dirdetails += "'''Shape:'''\n\n" + "\n\n".join(sdetlist) + "\n\n"
            # Platforms
            hsli = id2hslindex[rel.id]
            hslplatforms = ld["hslplatforms"]
            if hsli is not None:
                osmplatform = osm.route_platforms_or_stops(rel)
                are_stops = osmplatform and all(p[4].startswith('stop') for p in osmplatform)
                hslplatform = hslplatforms[hsli]
                # FIXME: Add stop names to unified diffs after diffing, somehow
                if md["agency"] == 'HSL' and platformidx == 2:
                    osmp = [re.sub(r"^([0-9]{4,4})$", r"H\1", p[2]) + "\n"\
                      for p in osmplatform]
                    hslp = [re.sub(r"^([0-9]{4,4})$", r"H\1", p[2]) + "\n"\
                      for p in hslplatform]
                else:
                    osmp = [p[platformidx]+"\n" for p in osmplatform]
                    hslp = [p[platformidx]+"\n" for p in hslplatform]
                diff = list(difflib.unified_diff(osmp, hslp, "OSM", md["agency"]))
                if not osmp or diff or are_stops:
                    dirdetails += "'''Platforms:'''\n\n"
                if are_stops:
                    dirdetails += "This route has platforms marked with role 'stop', role 'platform' is recommended.\n\n"
                if not osmp:
                    dirdetails += "{}/{} platforms in OSM / {}.\n\n".format(len(osmp), len(hslp), md["agency"])
                    cells.append((style_problem, "[[#{} | {}/{}]]".format(line, len(osmp), len(hslp))))
                elif diff:
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
                    cells.append((style_problem, "[[#{} | +{} -{}{}]]"\
                      .format(line, ins, rem, "(s)" if are_stops else "")))
                elif are_stops:
                    cells.append((style_maybe, "[[#{} | {}/{}(s)]]".format(line, len(osmp), len(hslp))))
                else:
                    cells.append((style_ok, "{}/{}".format(len(osmp), len(hslp))))
            else:
                dirdetails += "'''Platforms:'''\n\n"
                dirdetails += "Platforms could not be compared.\n\n"
                cells.append((style_problem, "[[#{} | N/A]]".format(line)))
            # Add per direction details
            if dirdetails:
                if hsli is not None:
                    ld["details"] += \
                      "'''Direction {}''', route [{} {}], [{} {}]\n\n"\
                        .format(dirindex, osm.relid2url(rel.id), rel.id,\
                          pattern2url(codes[hsli]),  codes[hsli]) + dirdetails
                else:
                    ld["details"] += \
                      "'''Direction {}''', route [{} {}], <No HSL route>\n\n"\
                        .format(dirindex, osm.relid2url(rel.id), rel.id) + dirdetails
            dirindex += 1
            # end 'for rel in rels'
        (linecounter, statcounter, lines_w_probs) = print_cells(cells, linecounter, statcounter, lines_w_probs)

    wr(footer)
    wr("")
    wr("{} lines total.\n".format(statcounter))
    wr("{} lines with differences.".format(lines_w_probs))

    # details
    if any(ld.get("details", None) for ld in md["lines"].values()):
        pass
        # No separate subheader for differences any more
        #wr("= Details on differences =\n")
    else:
        return
    for ld in [ md["lines"][ref] for ref in linerefs ]:
        if ld.get("details", None):
            wr("== {} ==".format(ld["lineref"]))
            wr(ld["details"])


def report_routes(md):
    """Write a mediawiki report page on routes with summary and line table."""
    print_abstract(md)
    print_summary(md)
    if md["mode"] == "bus":
        print_localbus(md)
    print_oldlines(md)
    if md["agency"] == "HSL" and md["mode"] == "ferry":
        linerefs = [ e['lineref'] for e in md["lines"].values() \
            if "htags" in e.keys() and not e["htags"]['gtfsId'].startswith('HSLlautta') ]
        print_routetable(md, linerefs)
        HSL_lautat = [ e['lineref'] for e in md["lines"].values() \
            if "htags" in e.keys() and e["htags"]['gtfsId'].startswith('HSLlautta') ]
        print_routetable(md, HSL_lautat, "Saaristoliikenne", 3)
    else:
        print_routetable(md)


def check_mode(os, ps):
    """Return a (style, text, details) tuple on mode related OSM tags."""
    modelist = osm.stoptags2mode(os)
    pmode = ps["mode"]
    if not modelist:
        details = "No mode found, provider has mode '{}'."\
          .format(pmode)
        return (style_problem, pmode, details)
    elif len(modelist) > 1:
        if pmode in modelist:
            m = "+".join(modelist)
            return (style_maybe, m, "")
        else:
            details = "OSM tags match modes: {}. provider has mode '{}'."\
              .format(", ".join(modelist), pmode)
            return (style_problem, pmode, details)
    else:
        omode = modelist[0]
        if omode == pmode:
            return (style_ok, omode, "")
        else:
            details = "Mode from OSM tags is '{}', provider has mode '{}'."\
              .format(omode, pmode)
            return (style_problem, pmode, details)


def check_type(os, _=None):
    type2style = {
        "node": style_ok,
        "way": style_maybe,
        "relation": style_problem,
    }
    osmtype = osm.xtype2osm[os["x:type"]]
    text = "[{} {}]".format(osm.obj2url(os), osmtype)
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


def shorten(s, maxlen=25):
    return s if len(s) < maxlen else s[:(maxlen-5)] + u"\u2026" + s[-3:]


def check_name(os, ps):
    """Return (style, text, details) cell tuple comparing name value."""
    maxlen = 25
    on = os.get("name", None)
    pn = hsl.get_stopname(ps)
    cn = pn if pn else "<no name in data>"
    cn = shorten(cn)
    if on:
        if on == pn:
            namefi = os.get("name:fi", None)
            namesv = os.get("name:sv", None)
            if namefi and namesv and namefi != on and namesv != on:
                details = "'''name:fi'''={} and '''name:sv'''={}, but '''name'''={}."\
                  .format(namefi, namesv, on)
                return (style_problem, cn, details)
            else:
                return (style_ok, cn, "")
        else:
            for abbr, repl in hsl.synonyms:
                if on.replace(repl, abbr) == pn:
                    return (style_ok, shorten(on), "")
            details = "'''name''' set to '{}', should be '{}'."\
              .format(on, pn)
            return (style_problem, cn, details)
    else:
        details = "'''name''' not set in OSM, provider has '{}'.".format(pn)
        return (style_problem, cn, details)


def check_findr(os, ps):
    """Return (style, text, details) tuple for ref:findr tag in OSM.
    Compares value to Digiroad data."""
    # FIXME: Should also compare by position, useless as it is now
    findr = os.get("ref:findr", None)
    import digiroad
    dlist = digiroad.stops_by_name.get(ps["name"], [])
    drid = None
    mindist = 1e6;
    olatlon = os["x:latlon"]
    for d in dlist:
        dist = haversine(olatlon, (float(d['stop_lat']), float(d['stop_lon'])))
        if dist < mindist:
            mindist = dist
            drid = d["stop_id"]
    if findr:
        if drid:
            if findr == drid:
                return (style_ok, str(findr), "")
            else:
                details = "'''ref:findr''' is '{}', should be '{}'."\
                  .format(findr, drid)
                return (style_problem, "diff", details)
        else:
            details = "'''ref:findr''' is set, but not found from Digiroad."
            return (style_maybe, "{}/-".format(findr), details)
    else:
        if drid:
            return (style_problem, str(drid), "")
        else:
#            details = "Digiroad ID for stop name '{}' missing."\
#              .format(ps["name"])
            details = ""
            return (style_problem, "N/A", details)


def check_zone(os, ps):
    """Return (style, text) cell tuple comparing zone:HSL value."""
    oz = os.get("zone:HSL", None)
    pz = ps.get("zoneId", "?")
    pz = "no" if pz == "Ei HSL" else pz
    if oz:
        if oz == pz:
            return (style_ok, oz)
        else:
            return (style_problem, "{}/{}".format(oz, pz))
    else:
        if pz == 'no':
            return (style_ok, "-/-")
        else:
            return (style_problem, "-/{}".format(pz))


def check_wheelchair(os, ps):
    """Return (cell style, text) string tuple comparing wheelchair
    accessibility for a stop."""
    ow = os.get("wheelchair", None)
    pw = ps.get("wheelchairBoarding", None)
    if not ow:
        if not pw:
            return (style_problem, "-/err1")
        elif pw == "NO_INFORMATION":
            return (style_ok, "-/?")
        elif pw == "POSSIBLE":
            return (style_problem, "-/yes")
        elif pw == "NOT_POSSIBLE":
            return (style_problem, "-/no")
        else:
            return (style_problem, "-/err2")
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


def print_stopline(oslist, ps, cols):
    """Print a line to stop table, return (nlines, isok)."""
    ref = ps["code"]
    # Prefer exact ref matches (i.e. Hnnnn), if there are none, use all
    flist = [ e for e in oslist if e.get("ref", None) == ref ]
    oslist = flist if flist else oslist
    linecounter = 1
    detlist = []
    wr("|-")
    wr("| [https://reittiopas.hsl.fi/pysakit/{} {}]"\
      .format(ps["gtfsId"], ref))
    isok = True
    if len(oslist) == 1:
        def wr_cell(f, o, p):
            tt = f(o, p)
            st = tt[0]
            txt = tt[1]
            if len(tt) > 2 and tt[2]:
                detlist.append(tt[2])
            wr('| style="{}" | {}'.format(st, txt))
            return st != style_problem

        os = oslist[0]
        isok &= wr_cell(check_name, os, ps)
        isok &= wr_cell(check_mode, os, ps)
        isok &= wr_cell(check_type, os, ps)
        isok &= wr_cell(check_dist, os, ps)
        isok &= wr_cell(check_zone, os, ps)
#        isok &= wr_cell(check_findr, os, ps)
        isok &= wr_cell(check_wheelchair, os, ps)
        if detlist:
            isok = False
            linecounter += len(detlist)
            wr('|-')
            wr('| colspan={} style="{}" | {}'.format(cols, style_details, "\n".join(detlist)))
    elif len(oslist) > 1:
        isok = False
        (lat, lon) = ps["latlon"]
        wr('| colspan={} style="{}" | More than one stop with the same ref in OSM'.format(cols-1, style_problem))
        wr('|-')
        desc = "\nMatching stops in OSM: {}.".format(", ".join(\
          [ "[https://www.openstreetmap.org/{}/{} {}]"\
          .format(osm.xtype2osm[e["x:type"]], e["x:id"], e["x:id"]) for e in oslist ]))
        wr('| colspan={} style="{}" | {}'.format(cols, style_details, desc))
        linecounter += 1
    else:
        isok = False
        (lat, lon) = ps["latlon"]
        wr('| colspan={} style="{}" | missing from [https://www.openstreetmap.org/#map=19/{}/{} OSM]'.format(cols-1, style_problem, lat, lon))
        wr('|-')
        taglist = []
        taglist.append("'''name'''='{}'".format(hsl.get_stopname(ps)))
        pz = ps.get("zoneId", None)
        if pz and pz != "Ei HSL":
            taglist.append(f"'''zone:HSL'''='{pz}'")
        pw = ps.get("wheelchairBoarding", None)
        if pw and pw == 'POSSIBLE':
            taglist.append("'''wheelchair'''='yes'")
        elif pw and pw == 'NOT_POSSIBLE':
            taglist.append("'''wheelchair'''='no'")
        desc = "Mode is {}. ".format(ps["mode"])
        desc += "Tags from provider: " + ", ".join(taglist) + "."
        wr('| colspan={} style="{}" | {}'.format(cols, style_details, desc))
        linecounter += 1
    return linecounter, isok


def print_stoptable_cluster(sd, refs=None):
    """Print a stoptable grouped by clusters, for clusters which contain
    at least one stop from refs."""
    cols = 6
    header = '{| class="wikitable"\n|-\n! colspan=%d | Cluster' % (cols)
    subheader = """|-
! ref
! name
! mode
! type
! delta
! wheelchair"""
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
    stopcounter = 0
    probcounter = 0
    wr(header)
    wr(subheader)
    for k in kk:
        if linecounter > 15:
            wr(subheader)
            linecounter = 0
        s = wc.get(k, None)
        if not s:
            continue
        c = pst[k]["cluster"]
        clist = list(set(pcl[c["gtfsId"]]))
        clist.sort()
        linecounter += 1
        wr("|-")
        wr("|colspan={} | {}".format(cols, c["name"]))
        for ref in clist:
            oslist = wc.pop(ref, [])
            ps = pst[ref]
            nlines, isok = print_stopline(oslist, ps, cols)
            linecounter += nlines
            stopcounter += 1
            probcounter += 0 if isok else 1
    wr(footer)
    wr("")
    wr("{} stops.\n".format(stopcounter))
    wr("{} stops with differences.\n".format(probcounter))
    wr("")


def print_stoptable(sd, stops=None):
    """Print a stoptable for stops."""
    cols = 7
    header = '{| class="wikitable"'
    subheader = """|-
! ref
! name
! mode
! type
! delta
! zone:HSL
! wheelchair"""
    footer = "|}"

    ost = sd["ost"]
    pst = sd["pst"] # data from provider

    if stops is None:
        stops = [ v for m in pst.keys() for v in pst[m].values() ]
        stops.sort(key=keykey("code"))

    linecounter = 0
    stopcounter = 0
    probcounter = 0
    wr(header)
    wr(subheader)
    for ps in stops:
        ref = ps["code"]
        if (zerocodepat.match(ref) and linecounter > 9) or linecounter > 30:
            wr(subheader)
            linecounter = 0
        oslist = ost.get(ref, [])
        nlines, isok = print_stopline(oslist, ps, cols)
        #linecounter += nlines
        linecounter += 1 # Makes diffs more stable
        stopcounter += 1
        probcounter += 0 if isok else 1
    wr(footer)
    wr("")
    wr("{} stops.\n".format(stopcounter))
    wr("{} stops with differences.\n".format(probcounter))


def report_stoptable_cluster(sd, city):
    prefixes = hsl.city2prefixes[city]
    pattern = re.compile("^(" + "|".join(prefixes) + ")[0-9]{4,4}$")
    pst = sd["pst"]
    refs = [ k for k in pst.keys() if pattern.match(k) ]
    print_stoptable_cluster(sd, refs)


def report_stops(sd, mode=None, city=None):
    """Output a report on stops. Either all, or limited by mode, city or both."""
    header = "= {} stops".format(sd["agency"]) if not mode \
      else "= {} {} stops".format(sd["agency"], mode)
    header += " =\n" if not city else " in {} =\n".format(city)
    wr("__FORCETOC__")
    wr("This is a comparison of OSM public transit stop data with [https://www.hsl.fi/ HSL] data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n")
    wr(header)

    ost = sd["ost"]
    pst = sd["pst"]

    if mode:
        stops = list(pst[mode].values())
        orefs = ( r for r, vl in ost.items() if mode in (m for v in vl for m in osm.stoptags2mode(v)) )
    else:
        stops = [ v for m in pst.keys() for v in pst[m].values() ]
        orefs = ost.keys()
    if city:
        prefixes = hsl.city2prefixes[city]
        # temporary(?) stops to be added to "Stops not in HSL" section
        prefixes.extend([ "X" + p for p in prefixes])
        pattern = re.compile("^(" + "|".join(prefixes) + ")[0-9]{4,4}$")
        stops = [ s for s in stops if pattern.match(s["code"]) ]
        orefs = (r for r in orefs if pattern.match(r))
    stops.sort(key=keykey("code"))
    print_stoptable(sd, stops)
    orefs = set(orefs)
    pstops = set(ps["code"] for ps in stops)
    extras = orefs.difference(pstops)
    hslpat = re.compile(r"^[^0-9]*[0-9]{4,4}$")
    extras = [ r for r in extras if hslpat.match(r) ]
    extras.sort()
    wr("= Stops not in HSL data =\n")
    wr("{} stops not in HSL:\n".format(len(extras)))
    wr(" " + " ".join(osm.stoplist2links(ost[ref]) for ref in extras))


def check_stationname(os, ps):
    """Return (style, text, details) cell tuple comparing station names."""
    # TODO: check that name:fi matches name
    on = os.get("name", None)
    pn = ps.get("name", None)
    complen = 4
    if on:
        if on == pn:
            return (style_ok, on, "")
        elif len(on) >= complen and pn.startswith(on[:complen]):
            return (style_maybe, on, "")
        else:
            return (style_problem, on, "")
    else:
        return (style_problem, "<no name in OSM>", "")


def print_stationline(os, ps, cols):
    def wr_cell(f, o, p):
        tt = f(o, p)
        st = tt[0]
        txt = tt[1]
        if len(tt) > 2 and tt[2]:
            detlist.append(tt[2])
        wr('| style="{}" | {}'.format(st, txt))
        return st != style_problem

    op = os.get("x:latlon", None)
    pp = ps.get("latlon", None)
    dist = haversine(op, pp)
    oname = os.get("name", "<no name>")
    linecounter = 1
    isok = True
    detlist = []
    wr("|-")
    wr("| [{} {}]".format(terminalid2url(ps["gtfsId"]), ps["name"]))
    if dist > 0.200:
        isok = False
        (lat, lon) = ps["latlon"]
        wr('| colspan={} style="{}" | Station not found in [https://www.openstreetmap.org/#map=19/{}/{} OSM]'.format(cols-1, style_problem, lat, lon))
    else:
        os["x:matched"] = True
        isok &= wr_cell(check_stationname, os, ps)
        isok &= wr_cell(check_mode, os, ps)
        isok &= wr_cell(check_type, os, ps)
        wr("| {0:.0f} m".format(dist*1000))
    if detlist:
        isok = False
        linecounter += len(detlist)
        wr('|-')
        wr('| colspan={} style="{}" | {}'.format(cols, style_details, "\n".join(detlist)))
    return linecounter, isok


def print_stationtable(sd, mode):
    """Print a table of 'mode' stations."""
    import numpy as np
    from pykdtree.kdtree import KDTree
    cols = 5
    header = '{| class="wikitable"'
    subheader = """|-
! HSL name
! OSM name
! mode
! type
! delta"""
    footer = "|}"

    ost = sd["ostat"]
    pst = sd["pstat"] # data from provider

    stations = pst[mode]
    stations.sort(key=keykey('name'))
    ostats = ost[mode]
    kd_tree = KDTree(np.array([e["x:latlon"] for e in ostats]))

    linecounter = 0
    statcounter = 0
    probcounter = 0
    wr(header)
    wr(subheader)
    for ind in range(len(stations)):
        if linecounter > 19:
            wr(subheader)
            linecounter = 0
        ps = stations[ind]
        darr, iarr = kd_tree.query(np.array(ps["latlon"], ndmin=2))
        oind = iarr[0]
        os = ostats[oind]
        nlines, isok = print_stationline(os, ps, cols)
        #linecounter += nlines
        linecounter += 1 # Makes diffs more stable
        statcounter += 1
        probcounter += 0 if isok else 1
    wr(footer)
    wr("")
    wr("{} stations.\n".format(statcounter))
    wr("{} stations with differences.\n".format(probcounter))
    not_in = [ s for s in ostats if not "x:matched" in s.keys() ]
    if not_in:
        not_in.sort(key=keykey("name"))
        wr("'''{} stations not in HSL'''\n".format(mode.capitalize()))
        sgen = ("[{} {}]".format(osm.obj2url(s), s.get("name", "<no name in OSM>")) for s in not_in)
        wr(" {}\n".format(", ".join(sgen)))


def report_stations(sd, mode=None):
    """Output a report on stations. Either all, or limited by mode."""
    ostat = sd["ostat"]
    pstat = sd["pstat"]
    wr("This is a comparison of OSM public transit station data with [https://www.hsl.fi/ HSL] data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n")
    if mode:
        modelist = [mode]
    else:
        modelist = list(pstat.keys())
        wr("= Stations in HSL =\n")
    modelist.sort()
    for m in modelist:
        wr("== {} stations ==".format(m.capitalize()))
        print_stationtable(sd, m)


def check_cbname(os, ps):
    """Return (style, text, details) cell tuple comparing citybike station name value."""
    stationext = {
        '': " kaupunkipyöräasema",
        ':fi': " kaupunkipyöräasema",
        ':en': " city bike station",
        ':sv':" stadscykelstation",
    }
    detlist = []
    isok = True
    for tagext, stext in stationext.items():
        onorig = os.get("name"+tagext, None)
        pn = ps.get("name"+tagext, None)
        if not pn:
            continue
        if onorig:
            on = onorig.replace(stext, "")
            if on == pn or any(pn.replace(repl, abbr) == on for repl, abbr in hsl.synonyms):
                isok &= True
            else:
                detlist.append(f"'''name{tagext}''' set to '{onorig}', should be '{pn}{stext}'.")
                isok = False
        else:
            if tagext != ':fi':
                detlist.append(f"'''name{tagext}''' not set in OSM, should be '{pn}{stext}'.")
            if tagext == '':
                isok = False

    on = os.get("name", "").replace(" kaupunkipyöräasema", "")
    pn = ps["name"]
    if on == pn or any(pn.replace(repl, abbr) == on for repl, abbr in hsl.synonyms):
        goodname = on
    else:
        goodname = pn

    return (style_ok if isok else style_problem, goodname, "\n".join(detlist))


def check_capacity(os, ps):
    """Return (style, text, details) cell tuple comparing citybike station capacity."""
    oc = os.get("capacity", None)
    if ps["state"] != 'Station on':
        cell = "{} / N/A".format(oc if oc else "-")
        return (style_maybe, cell, "")
    #pc = str(int(ps['bikesAvailable']) + int(ps['spacesAvailable']))
    pc = ps.get("total_slots", "?")
    if oc:
        if oc == pc:
            return (style_ok, pc, "")
        else:
            cell = "{}/{}".format(oc, pc)
            #details = "'''capacity'''='{}', should be '{}'.".format(oc, pc)
            return (style_problem, cell, "")
    else:
        cell = "-/{}".format(pc)
        #details = "'''capacity''' not set in OSM, HSL has '{}'.".format(pc)
        return (style_problem, cell, "")


def print_citybikeline(oslist, ps, cols):
    """Print a line to citybike table, return (nlines, isok)."""
    ref = ps["stationId"]
    linecounter = 1
    detlist = []
    wr("|-")
    wr("| [{} {}]".format(citybike2url(ref), ref))
    isok = True
    if len(oslist) == 1:
        def wr_cell(f, o, p):
            tt = f(o, p)
            st = tt[0]
            txt = tt[1]
            if len(tt) > 2 and tt[2]:
                detlist.append(tt[2])
            wr('| style="{}" | {}'.format(st, txt))
            return st != style_problem

        os = oslist[0]
        isok &= wr_cell(check_cbname, os, ps)
        isok &= wr_cell(check_type, os, ps)
        isok &= wr_cell(check_dist, os, ps)
        isok &= wr_cell(check_capacity, os, ps)
        if detlist:
            isok = False
            linecounter += len(detlist)
            wr('|-')
            wr('| colspan={} style="{}" | {}'.format(cols, style_details, "\n".join(detlist)))
    elif len(oslist) > 1:
        isok = False
        wr('| {}'.format(ps["name"]))
        (lat, lon) = ps["latlon"]
        wr('| colspan={} style="{}" | More than one station with the same ref in OSM'.format(cols-2, style_problem))
        wr('|-')
        desc = "\nMatching stations in OSM: {}.".format(", ".join(\
          [ "[https://www.openstreetmap.org/{}/{} {}]"\
          .format(osm.xtype2osm[e["x:type"]], e["x:id"], e["x:id"]) for e in oslist ]))
        wr('| colspan={} style="{}" | {}'.format(cols, style_details, desc))
        linecounter += 1
    else:
        isok = False
        wr('| {}'.format(ps["name"]))
        (lat, lon) = ps["latlon"]
        wr('| colspan={} style="{}" | missing from [https://www.openstreetmap.org/#map=19/{}/{} OSM]'.format(cols-2, style_problem, lat, lon))
        wr('|-')
        taglist = []
        taglist.append("'''name'''='{}'".format(ps["name"]))
#        if ps["state"] == 'Station on':
#            cap = str(int(ps['bikesAvailable']) + int(ps['spacesAvailable']))
#            taglist.append("'''capacity'''='{}'".format(cap))
#        if "total_slots" in ps.keys():
#            taglist.append("'''capacity'''='{}'".format(ps["total_slots"]))
        desc = "Tags from HSL: " + ", ".join(taglist) + "."
        wr('| colspan={} style="{}" | {}'.format(cols, style_details, desc))
        linecounter += 1
    return linecounter, isok


def print_citybiketable(sd, refs=None):
    """Print a table of citybike stations."""
    cols = 6
    header = '{| class="wikitable"'
    subheader = """|-
! ref
! name
! type
! delta
! capacity"""
    footer = "|}"

    ost = sd["ocbs"].copy()
    pst = sd["pcbs"] # data from provider

    refs = refs if refs is not None else [e for e in pst.keys()]
    refs.sort(key=linesortkey)

    linecounter = 0
    statcounter = 0
    probcounter = 0
    wr(header)
    wr(subheader)
    for ref in refs:
        if (zerocodepat.match(ref) and linecounter > 9) or linecounter > 30:
            wr(subheader)
            linecounter = 0
        ps = pst[ref]
        if not ps["networks"][0] in ["vantaa", "smoove"]: continue
        oslist = ost.pop(ref, [])
        nlines, isok = print_citybikeline(oslist, ps, cols)
        #linecounter += nlines
        linecounter += 1 # Makes diffs more stable
        statcounter += 1
        probcounter += 0 if isok else 1
    wr(footer)
    wr("")
    wr("{} citybike stations.\n".format(statcounter))
    wr("{} citybike stations with differences.\n".format(probcounter))


def report_citybikes(sd):
    """Output a report on citybike stations."""
    ost = sd["ocbs"]
    pst = sd["pcbs"]
    wr("__FORCETOC__")
    wr("This is a comparison of OSM citybike station data with [https://www.hsl.fi/ HSL] data (via [http://digitransit.fi digitransit.fi]) generated by a [https://github.com/tpikonen/taival script].\n")
    #wr("= Citybike stations in HSL =\n")

    wr("== Active citybike stations ==\n")
    active_refs = [ v["stationId"] for v in pst.values() if v["state"] == "Station on" ]
    print_citybiketable(sd, active_refs)

    wr("== Citybike stations not in use ==\n")
    inactive_refs = [ v["stationId"] for v in pst.values() if v["state"] != "Station on" ]
    print_citybiketable(sd, inactive_refs)

    wr("== Other citybike stations ==\n")
    printedset = set(active_refs + inactive_refs)
    rest_w_ref = [ e for l in ost.values() for e in l if not e["ref"] in printedset ]
    rest_w_ref.sort(key=lambda x: linesortkey(keykey("ref")(x)))
    orest = list(sd["orest"].values())
    orest.sort(key=keykey("name"))
    wr("{} citybike stations not in {}:\n".format(len(rest_w_ref) + len(orest), sd["agency"]))
    rlist = ["[{} {}]".format(osm.obj2url(s), s.get("ref", "<no ref in OSM>")) for s in rest_w_ref]
    olist = ["[{} {}]".format(osm.obj2url(s), s.get("name", "<no name in OSM>")) for s in orest]
    wr(" {}\n".format(", ".join(rlist + olist)))
